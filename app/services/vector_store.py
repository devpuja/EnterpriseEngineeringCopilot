from pathlib import Path
from typing import Any, cast

import chromadb
import numpy as np

from app.services.document_ingestion import DocumentChunk, stable_chunk_id


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

    def get_neighbor_chunks(
        self,
        results: list[dict[str, Any]],
        radius: int = 1,
    ) -> list[dict[str, Any]]:
        """Expand semantic hits with nearby chunks from the same document only."""
        expanded: dict[tuple[str, int], dict[str, Any]] = {}

        for result in results:
            raw_metadata = result.get("metadata")
            metadata: dict[str, Any] = cast(dict[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
            document_id = str(metadata.get("document_id", ""))
            chunk_index = metadata.get("chunk_index")
            if not document_id or not isinstance(chunk_index, int):
                continue

            neighbor_ids: list[str] = []
            for offset in range(-radius, radius + 1):
                neighbor_index = chunk_index + offset
                if neighbor_index < 0:
                    continue
                neighbor_ids.append(stable_chunk_id(document_id, neighbor_index))

            try:
                neighbors = self._collection.get(
                    ids=neighbor_ids,
                    include=["documents", "metadatas"],
                )
            except Exception:
                continue

            neighbor_ids_found = neighbors["ids"] or []
            neighbor_documents = neighbors["documents"] or []
            neighbor_metadatas = neighbors["metadatas"] or []

            for chunk_id, text, metadata_value in zip(
                neighbor_ids_found,
                neighbor_documents,
                neighbor_metadatas,
            ):
                normalized_metadata: dict[str, Any] = cast(
                    dict[str, Any], metadata_value
                ) if isinstance(metadata_value, dict) else {}
                neighbor_document_id = str(normalized_metadata.get("document_id", ""))
                neighbor_index = normalized_metadata.get("chunk_index")
                if neighbor_document_id != document_id or not isinstance(neighbor_index, int):
                    continue
                expanded[(neighbor_document_id, neighbor_index)] = {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": normalized_metadata,
                    "distance": result.get("distance"),
                }

        return [expanded[key] for key in sorted(expanded, key=lambda item: (item[0], item[1]))]

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
