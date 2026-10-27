from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import app.rag.factory as factory_module
import app.rag.service as service_module
from app.rag.models import DocumentChunk
from app.rag.document_store import AzureBlobDocumentStore
from app.rag.embeddings import FoundryEmbeddingProvider
from app.rag.search_index import AzureAISearchIndex
from app.rag.search_index import InMemorySearchIndex
from app.rag.service import RagService


class FakeDocumentStore:
    def __init__(self):
        self.saved = []

    def save(self, **kwargs):
        self.saved.append(kwargs)
        return "fake://stored"


class FakeEmbeddings:
    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 2.0]


@pytest.mark.parametrize("backend", ["memory", " AZURE "])
def test_factory_uses_configured_backend(monkeypatch, backend):
    monkeypatch.setattr(factory_module.settings, "rag_backend", backend)
    monkeypatch.setattr(factory_module.settings, "rag_chunk_size", 600)
    monkeypatch.setattr(factory_module.settings, "rag_chunk_overlap", 50)
    monkeypatch.setenv("RAG_BACKEND", "unsupported")
    azure = backend.strip().lower() == "azure"
    index_class = "AzureAISearchIndex" if azure else "InMemorySearchIndex"
    store_class = "AzureBlobDocumentStore" if azure else "LocalDocumentStore"

    with (
        patch.object(factory_module, index_class) as index,
        patch.object(factory_module, store_class) as store,
        patch.object(factory_module, "FoundryEmbeddingProvider") as embeddings,
        patch.object(factory_module, "RagService") as service,
    ):
        result = factory_module.get_rag_service.__wrapped__()

    assert result is service.return_value
    index.assert_called_once_with()
    store.assert_called_once_with()
    assert service.call_args.kwargs["search_index"] is index.return_value
    assert service.call_args.kwargs["document_store"] is store.return_value
    if azure:
        embeddings.assert_called_once_with()
        assert service.call_args.kwargs["embedding_provider"] is embeddings.return_value
        assert service.call_args.kwargs["chunk_size"] == 600
        assert service.call_args.kwargs["chunk_overlap"] == 50
    else:
        embeddings.assert_not_called()


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setattr(factory_module.settings, "rag_backend", "unsupported")
    with pytest.raises(RuntimeError, match="RAG_BACKEND"):
        factory_module.get_rag_service.__wrapped__()


def test_search_adapter_uses_shared_settings(monkeypatch):
    config = factory_module.settings
    monkeypatch.setattr(config, "azure_search_endpoint", "https://example.search.windows.net")
    monkeypatch.setattr(config, "azure_search_index_name", "test-index")
    monkeypatch.setattr(config, "azure_search_api_key", "test-key")
    monkeypatch.setattr(config, "rag_embedding_dimensions", 3072)
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    with (
        patch("azure.search.documents.SearchClient") as client,
        patch("azure.search.documents.indexes.SearchIndexClient") as index_client,
    ):
        index_client.return_value.list_indexes.return_value = []
        AzureAISearchIndex()

    assert client.call_args.kwargs["endpoint"] == config.azure_search_endpoint
    assert client.call_args.kwargs["index_name"] == "test-index"
    assert client.call_args.kwargs["credential"].key == "test-key"
    schema = index_client.return_value.create_index.call_args.args[0]
    vector_field = next(field for field in schema.fields if field.name == "content_vector")
    assert vector_field.vector_search_dimensions == 3072


@pytest.mark.parametrize("use_connection_string", [False, True])
def test_blob_adapter_uses_shared_settings(monkeypatch, use_connection_string):
    config = factory_module.settings
    monkeypatch.setattr(config, "azure_storage_account_url", "https://example.blob.core.windows.net")
    monkeypatch.setattr(config, "azure_storage_container", "test-documents")
    monkeypatch.setattr(
        config, "azure_storage_connection_string",
        "test-connection-string" if use_connection_string else "",
    )
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    with (
        patch("azure.storage.blob.BlobServiceClient") as client,
        patch("azure.identity.DefaultAzureCredential") as credential,
    ):
        AzureBlobDocumentStore()

    if use_connection_string:
        client.from_connection_string.assert_called_once_with("test-connection-string")
        service = client.from_connection_string.return_value
        credential.assert_not_called()
    else:
        client.assert_called_once_with(
            config.azure_storage_account_url, credential=credential.return_value
        )
        service = client.return_value
    service.get_container_client.assert_called_once_with("test-documents")


def test_foundry_embeddings_use_shared_settings(monkeypatch):
    config = factory_module.settings
    monkeypatch.setattr(config, "foundry_openai_endpoint", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.setattr(config, "foundry_embedding_model", "test-embeddings")
    monkeypatch.setattr(config, "rag_embedding_dimensions", 3072)
    monkeypatch.delenv("FOUNDRY_OPENAI_ENDPOINT", raising=False)
    provider = FoundryEmbeddingProvider()
    assert provider._endpoint == config.foundry_openai_endpoint
    assert provider._model == "test-embeddings"
    assert provider._dimensions == 3072


@pytest.mark.parametrize(
    ("adapter", "missing_fields", "message"),
    [
        (AzureAISearchIndex, ["azure_search_endpoint"], "AZURE_SEARCH_ENDPOINT"),
        (
            AzureBlobDocumentStore,
            ["azure_storage_account_url", "azure_storage_connection_string"],
            "AZURE_STORAGE_ACCOUNT_URL",
        ),
        (FoundryEmbeddingProvider, ["foundry_openai_endpoint"], "FOUNDRY_OPENAI_ENDPOINT"),
        (FoundryEmbeddingProvider, ["foundry_embedding_model"], "FOUNDRY_EMBEDDING_MODEL"),
    ],
)
def test_azure_adapters_reject_missing_configuration(monkeypatch, adapter, missing_fields, message):
    monkeypatch.setattr(factory_module.settings, "foundry_project_endpoint", "https://example.test")
    for field in missing_fields:
        monkeypatch.setattr(factory_module.settings, field, "")
    with pytest.raises(RuntimeError, match=message):
        adapter()


def test_ingest_pdf_chunks_indexes_and_persists_source(monkeypatch):
    monkeypatch.setattr(service_module, "extract_pdf_text", lambda _: ("CAP theorem. Consistency and partition tolerance." * 5, 1))
    store = FakeDocumentStore()
    index = InMemorySearchIndex()
    service = RagService(search_index=index, document_store=store, chunk_size=50, chunk_overlap=10)

    result = service.ingest_pdf(tenant_id="tenant-a", file_name="architecture.pdf", pdf_bytes=b"fake-pdf")

    assert result["status"] == "indexed"
    assert result["chunk_count"] > 1
    assert store.saved[0]["tenant_id"] == "tenant-a"
    assert store.saved[0]["file_name"] == "architecture.pdf"
    retrieved = service.retrieve(tenant_id="tenant-a", question="CAP theorem", top_k=3)
    assert retrieved
    assert all(item.file_name == "architecture.pdf" for item in retrieved)
    assert all(item.version == 1 for item in retrieved)


def test_retrieval_enforces_tenant_filter():
    index = InMemorySearchIndex()
    store = FakeDocumentStore()
    chunks = [
        DocumentChunk("a1", "doc-a", "tenant-a", "a.pdf", 1, 0, "Azure Service Bus queue", "h1"),
        DocumentChunk("b1", "doc-b", "tenant-b", "b.pdf", 1, 0, "Azure Service Bus queue", "h2"),
    ]
    index.upsert_chunks(chunks)
    service = RagService(search_index=index, document_store=store)
    results = service.retrieve(tenant_id="tenant-a", question="Service Bus", top_k=5)
    assert len(results) == 1
    assert results[0].document_id == "doc-a"


def test_retrieve_rejects_unsafe_tenant_id():
    service = RagService(search_index=InMemorySearchIndex(), document_store=FakeDocumentStore())
    with pytest.raises(ValueError, match="tenant_id"):
        service.retrieve(tenant_id="../tenant-b", question="test")


def test_ingest_rejects_non_pdf_filename():
    service = RagService(search_index=InMemorySearchIndex(), document_store=FakeDocumentStore())
    with pytest.raises(ValueError, match=r"\.pdf"):
        service.ingest_pdf(tenant_id="tenant-a", file_name="notes.txt", pdf_bytes=b"not a pdf")


def test_azure_embedding_provider_is_not_required_for_local_backend():
    service = RagService(search_index=InMemorySearchIndex(), document_store=FakeDocumentStore())
    assert service.retrieve(tenant_id="tenant-a", question="nothing here") == []


def test_duplicate_filename_is_rejected_until_versioned_updates_are_implemented(monkeypatch):
    monkeypatch.setattr(service_module, "extract_pdf_text", lambda _: ("PDF content about RAG.", 1))
    service = RagService(search_index=InMemorySearchIndex(), document_store=FakeDocumentStore())
    service.ingest_pdf(tenant_id="tenant-a", file_name="guide.pdf", pdf_bytes=b"first-pdf")
    with pytest.raises(FileExistsError, match="Versioned updates"):
        service.ingest_pdf(tenant_id="tenant-a", file_name="guide.pdf", pdf_bytes=b"updated-pdf")
