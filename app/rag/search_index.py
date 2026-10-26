from __future__ import annotations

import re
from collections import Counter
from typing import Any, Protocol

from app.config.settings import settings
from app.rag.models import DocumentChunk


class SearchIndex(Protocol):
    def document_exists(self, *, tenant_id: str, document_id: str) -> bool: ...
    def upsert_chunks(self, chunks: list[DocumentChunk], vectors: list[list[float]] | None = None) -> None: ...
    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]: ...


class InMemorySearchIndex:
    """Local development/test adapter. Lexical ranking only; not semantic search."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    def document_exists(self, *, tenant_id: str, document_id: str) -> bool:
        return any(
            item["tenant_id"] == tenant_id and item["document_id"] == document_id and item["is_active"]
            for item in self._documents.values()
        )

    def upsert_chunks(self, chunks: list[DocumentChunk], vectors: list[list[float]] | None = None) -> None:
        if vectors is not None and len(vectors) != len(chunks):
            raise ValueError("The number of vectors must match the number of chunks.")
        for index, chunk in enumerate(chunks):
            item = chunk.to_search_document(vectors[index] if vectors else None)
            self._documents[chunk.chunk_id] = item

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        del query_vector  # The local adapter intentionally does lexical ranking only.
        terms = set(re.findall(r"[a-z0-9_]+", query.lower()))
        if not terms:
            return []
        matches: list[dict[str, Any]] = []
        for document in self._documents.values():
            if document["tenant_id"] != tenant_id or not document["is_active"]:
                continue
            content_terms = re.findall(r"[a-z0-9_]+", document["content"].lower())
            counts = Counter(content_terms)
            score = sum(counts[term] for term in terms)
            if score:
                item = dict(document)
                item["score"] = float(score)
                matches.append(item)
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[:top_k]


class AzureAISearchIndex:
    """Azure AI Search hybrid/vector adapter; creates the baseline index if absent."""

    def __init__(self) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.identity import DefaultAzureCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SearchableField,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )

        endpoint = settings.azure_search_endpoint.strip()
        index_name = settings.azure_search_index_name.strip()
        api_key = settings.azure_search_api_key.strip()
        dimensions = settings.rag_embedding_dimensions
        
        if not endpoint:
            raise RuntimeError("AZURE_SEARCH_ENDPOINT must be configured for Azure AI Search.")

        credential = AzureKeyCredential(api_key) if api_key else DefaultAzureCredential()
        index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        fields = [
            SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="tenant_id", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="file_name", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="version", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="content_hash", type=SearchFieldDataType.String),
            SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True),
            SimpleField(name="is_active", type=SearchFieldDataType.Boolean, filterable=True),
            SimpleField(name="uploaded_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=dimensions,
                vector_search_profile_name="rag-vector-profile",
            ),
        ]
        
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="rag-hnsw")],
            profiles=[VectorSearchProfile(name="rag-vector-profile", algorithm_configuration_name="rag-hnsw")],
        )
        
        existing = {item.name for item in index_client.list_indexes()}
        
        if index_name not in existing:
            index_client.create_index(SearchIndex(name=index_name, fields=fields, vector_search=vector_search))

        self._client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
        self._dimensions = dimensions


    def document_exists(self, *, tenant_id: str, document_id: str) -> bool:
        safe_tenant = tenant_id.replace("'", "''")
        safe_document = document_id.replace("'", "''")
        results = self._client.search(
            search_text="*",
            filter=f"tenant_id eq '{safe_tenant}' and document_id eq '{safe_document}' and is_active eq true",
            top=1,
            select=["chunk_id"],
        )
        return next(iter(results), None) is not None


    def upsert_chunks(self, chunks: list[DocumentChunk], vectors: list[list[float]] | None = None) -> None:
        if vectors is None or len(vectors) != len(chunks):
            raise ValueError("Azure AI Search ingestion requires one embedding vector per chunk.")
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self._dimensions}, got {len(vector)}. "
                    "Set RAG_EMBEDDING_DIMENSIONS to match the deployed embedding model."
                )
        documents = [chunk.to_search_document(vector) for chunk, vector in zip(chunks, vectors)]
        if documents:
            results = self._client.upload_documents(documents=documents)
            failures = [result for result in results if not result.succeeded]
            if failures:
                raise RuntimeError(f"Azure AI Search failed to index {len(failures)} chunk(s).")


    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        from azure.search.documents.models import VectorizedQuery

        safe_tenant = tenant_id.replace("'", "''")
        kwargs: dict[str, Any] = {
            "search_text": query,
            "filter": f"tenant_id eq '{safe_tenant}' and is_active eq true",
            "top": top_k,
            "select": [
                "chunk_id", "document_id", "tenant_id", "file_name", "version",
                "chunk_index", "content", "content_hash", "page_number", "is_active", "uploaded_at",
            ],
        }
        if query_vector is not None:
            kwargs["vector_queries"] = [
                VectorizedQuery(vector=query_vector, k_nearest_neighbors=top_k, fields="content_vector")
            ]
        results = self._client.search(**kwargs)
        return [
            {
                **{key: result.get(key) for key in (
                    "chunk_id", "document_id", "tenant_id", "file_name", "version",
                    "chunk_index", "content", "page_number", "is_active", "uploaded_at",
                )},
                "score": float(result.get("@search.score", 0.0)),
            }
            for result in results
        ]
