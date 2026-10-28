from pathlib import Path
from typing import Any

import chromadb
import numpy as np

from app.services.document_ingestion import DocumentChunk


class ChromaVectorStore:
    def __init__(self, persist_directory: str, collection_name: str) -> None:
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def replace_document(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Each chunk must have one embedding.")
        document_ids = {chunk.document_id for chunk in chunks}
        if len(document_ids) != 1:
            raise ValueError("A batch can only replace one document.")
        document_id = next(iter(document_ids))
        self.delete_document(document_id)
        self._collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=np.asarray(embeddings, dtype=np.float32),
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number if chunk.page_number is not None else -1,
                }
                for chunk in chunks
            ],
        )

    def delete_document(self, document_id: str) -> None:
        try:
            existing = self._collection.get(where={"document_id": document_id})
            if existing["ids"]:
                self._collection.delete(ids=existing["ids"])
        except Exception:
            # Collection deletes should remain explicit and predictable.
            self._collection.delete(where={"document_id": document_id})

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            return []
        effective_top_k = min(top_k, self._collection.count())
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=effective_top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0] if result["ids"] else []
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []
        return [
            {
                "chunk_id": chunk_id,
                "text": text,
                "metadata": metadata,
                "distance": distance,
            }
            for chunk_id, text, metadata, distance in zip(
                ids, documents, metadatas, distances
            )
        ]
