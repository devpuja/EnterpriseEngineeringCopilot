from __future__ import annotations

from functools import lru_cache

from app.config.settings import settings
from app.rag.document_store import AzureBlobDocumentStore, LocalDocumentStore
from app.rag.embeddings import FoundryEmbeddingProvider
from app.rag.search_index import AzureAISearchIndex, InMemorySearchIndex
from app.rag.service import RagService


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    backend = settings.rag_backend.strip().lower()
    if backend == "memory":
        # Explicit local development mode. This is in-memory search plus local files;
        # it is not semantic vector retrieval and data is not durable across restarts.
        return RagService(
            search_index=InMemorySearchIndex(),
            document_store=LocalDocumentStore(),
        )
    if backend == "azure":
        return RagService(
            search_index=AzureAISearchIndex(),
            document_store=AzureBlobDocumentStore(),
            embedding_provider=FoundryEmbeddingProvider(),
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
    raise RuntimeError("RAG_BACKEND must be 'memory' or 'azure'.")
