from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.rag.chunking import chunk_text
from app.rag.document_store import DocumentStore
from app.rag.embeddings import EmbeddingProvider
from app.rag.models import DocumentChunk, RetrievedChunk
from app.rag.pdf_extractor import extract_pdf_text
from app.rag.search_index import SearchIndex


class RagService:
    def __init__(
        self,
        *,
        search_index: SearchIndex,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
    ) -> None:
        self._index = search_index
        self._document_store = document_store
        self._embeddings = embedding_provider
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def _embed_many(self, texts: list[str]) -> list[list[float]] | None:
        if self._embeddings is None:
            return None
        if not texts:
            return []

        batch_method = getattr(self._embeddings, "embed_many", None)
        if callable(batch_method):
            # Keep each request small to reduce pressure on Azure embedding
            # rate limits while still using the provider's batch API.
            batch_size = 16
            vectors: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                batch_vectors = batch_method(batch)
                if len(batch_vectors) != len(batch):
                    raise RuntimeError(
                        "Embedding provider returned a different number of "
                        f"vectors than inputs: expected {len(batch)}, "
                        f"received {len(batch_vectors)}."
                    )
                vectors.extend(batch_vectors)
            return vectors

        # Compatibility with existing/test providers implementing only embed().
        return [self._embeddings.embed(text) for text in texts]


    def ingest_pdf(self, *, tenant_id: str, file_name: str, pdf_bytes: bytes) -> dict[str, Any]:
        if not tenant_id.strip() or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", tenant_id):
            raise ValueError("tenant_id must contain only letters, digits, dot, underscore, or hyphen.")
        
        safe_name = Path(file_name).name
        
        if safe_name != file_name or not safe_name.lower().endswith(".pdf"):
            raise ValueError("Only files with a .pdf extension are accepted.")
        
        if len(pdf_bytes) > 25 * 1024 * 1024:
            raise ValueError("PDF exceeds the 25 MiB Phase 3.1 upload limit.")

        text, _page_count = extract_pdf_text(pdf_bytes)
        document_hash = hashlib.sha256(pdf_bytes).hexdigest()
        document_id = hashlib.sha256(f"{tenant_id}:{safe_name}".encode("utf-8")).hexdigest()[:32]
        
        if self._index.document_exists(tenant_id=tenant_id, document_id=document_id):
            raise FileExistsError(
                "A document with this filename is already indexed for this tenant. "
                "Versioned updates are implemented in Phase 3.2; use a new filename for this baseline."
            )
        
        self._document_store.save(
            tenant_id=tenant_id,
            document_id=document_id,
            file_name=safe_name,
            content=pdf_bytes,
        )

        pieces = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)
        
        if not pieces:
            raise ValueError("PDF did not contain text that could be indexed.")
        
        timestamp = datetime.now(timezone.utc).isoformat()
        chunks = [
            DocumentChunk(
                chunk_id=hashlib.sha256(f"{tenant_id}:{document_id}:1:{i}:{document_hash}".encode()).hexdigest(),
                document_id=document_id,
                tenant_id=tenant_id,
                file_name=safe_name,
                version=1,
                chunk_index=i,
                content=piece,
                content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                is_active=True,
                uploaded_at=timestamp,
            )
            for i, piece in enumerate(pieces)
        ]

        vectors = self._embed_many([chunk.content for chunk in chunks])
 
        self._index.upsert_chunks(chunks, vectors)
 
        return {
            "document_id": document_id,
            "file_name": safe_name,
            "version": 1,
            "chunk_count": len(chunks),
            "status": "indexed",
        }


    def retrieve(self, *, tenant_id: str, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not tenant_id.strip() or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", tenant_id):
            raise ValueError("tenant_id must contain only letters, digits, dot, underscore, or hyphen.")
        
        if not question.strip():
            raise ValueError("question must not be empty")
        
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")
        
        query_vectors = self._embed_many([question])
        query_vector = query_vectors[0] if query_vectors else None
        results = self._index.search(
            question,
            tenant_id=tenant_id,
            top_k=top_k,
            query_vector=query_vector,
        )

        return [
            RetrievedChunk(
                chunk_id=str(item.get("chunk_id", "")),
                document_id=str(item.get("document_id", "")),
                file_name=str(item.get("file_name", "")),
                version=int(item.get("version", 1)),
                chunk_index=int(item.get("chunk_index", 0)),
                content=str(item.get("content", "")),
                score=float(item.get("score", 0.0)),
                page_number=int(item["page_number"]) if item.get("page_number") else None,
            )
            for item in results
        ]