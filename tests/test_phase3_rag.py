import pytest

from app.api.schemas import IndexedDocument
from app.services.document_ingestion import (
    DocumentIngestionError,
    ingest_document,
    split_text,
    stable_document_id,
)
from app.services.document_repository import DocumentRepository
from app.services.embedding_service import DeterministicEmbeddingService, OpenAIEmbeddingService, EmbeddingServiceError
from app.services.vector_store import ChromaVectorStore
from app.services.rag_service import RAGService


def test_txt_ingestion_chunks_with_metadata():
    content = b"Enterprise architecture relies on clear boundaries and tested interfaces."
    document_id, chunks = ingest_document("guide.txt", "text/plain", content, 100, 20)
    assert document_id == stable_document_id("guide.txt", content)
    assert len(chunks) == 1
    assert chunks[0].filename == "guide.txt"
    assert chunks[0].page_number is None
    assert chunks[0].document_id == document_id


def test_chunk_overlap_and_invalid_configuration():
    chunks = split_text("abcdefghij" * 30, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert chunks[0][-20:] == chunks[1][:20]
    with pytest.raises(ValueError):
        split_text("text", chunk_size=50, overlap=10)


def test_empty_and_unsafe_txt_inputs_are_rejected():
    with pytest.raises(DocumentIngestionError, match="no readable text"):
        ingest_document("empty.txt", "text/plain", b"", 100, 20)
    with pytest.raises(DocumentIngestionError, match="UTF-8"):
        ingest_document("bad.txt", "text/plain", b"\xff\xfe", 100, 20)


def test_deterministic_embeddings_are_dimensions_consistent():
    provider = DeterministicEmbeddingService()
    vectors = provider.embed(["alpha", "beta"])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1]) == 32


def test_openai_embedding_requires_api_key():
    with pytest.raises(EmbeddingServiceError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingService(api_key="")


def test_vector_store_insert_search_delete_and_persistence(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "test_collection")
    _, chunks = ingest_document("guide.txt", "text/plain", b"Architecture boundaries and API contracts.", 100, 20)
    embeddings = provider.embed([chunk.text for chunk in chunks])
    store.replace_document(chunks, embeddings)
    result = store.search(provider.embed(["architecture API"])[0], top_k=5)
    assert result
    assert result[0]["metadata"]["filename"] == "guide.txt"

    reopened = ChromaVectorStore(str(tmp_path / "chroma"), "test_collection")
    assert reopened.search(provider.embed(["architecture"])[0], top_k=5)
    reopened.delete_document(chunks[0].document_id)
    assert reopened.search(provider.embed(["architecture"])[0], top_k=5) == []


def test_document_repository_crud(tmp_path):
    repository = DocumentRepository(str(tmp_path / "metadata.db"))
    record = {
        "document_id": "doc1", "filename": "guide.txt", "media_type": "text/plain",
        "size_bytes": 12, "chunk_count": 2, "status": "indexed", "error": None,
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    }
    repository.upsert(record)
    assert repository.get("doc1")["status"] == "indexed"
    assert repository.list()[0]["document_id"] == "doc1"
    assert repository.delete("doc1") is True
    assert repository.get("doc1") is None


@pytest.mark.asyncio
async def test_empty_retrieval_answer_is_explicit(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "empty_collection")
    repository = DocumentRepository(str(tmp_path / "metadata.db"))
    service = RAGService(provider, store, repository, str(tmp_path / "docs"), 100, 20, 5, 12000)
    answer = await service.answer("What does the document say?")
    assert answer.grounded is False
    assert answer.sources == []
    assert "enough information" in answer.answer.lower()
