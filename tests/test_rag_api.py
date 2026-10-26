import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.rag as rag_api
from app.rag.models import RetrievedChunk


@pytest.fixture(autouse=True)
def use_memory_backend(monkeypatch):
    monkeypatch.setattr(rag_api.settings, "rag_backend", "memory")


class FakeService:
    def retrieve(self, *, tenant_id, question, top_k):
        assert tenant_id == "tenant-a"
        assert question == "What is RAG?"
        assert top_k == 2
        return [RetrievedChunk(
            chunk_id="chunk-1", document_id="doc-1", file_name="guide.pdf",
            version=1, chunk_index=0, content="RAG retrieves evidence.", score=1.0,
        )]

    def ingest_pdf(self, *, tenant_id, file_name, pdf_bytes):
        assert tenant_id == "tenant-a"
        assert file_name == "guide.pdf"
        assert pdf_bytes == b"%PDF-test"
        return {"document_id": "doc-1", "file_name": file_name, "version": 1, "chunk_count": 1, "status": "indexed"}


class FakeAnswerAgent:
    async def answer(self, question, chunks):
        return "RAG retrieves relevant evidence [chunk-1]."


def make_client():
    app = FastAPI()
    app.include_router(rag_api.router)
    return TestClient(app)


def test_query_endpoint_returns_answer_and_citations(monkeypatch):
    monkeypatch.setattr(rag_api, "get_rag_service", lambda: FakeService())
    monkeypatch.setattr(rag_api, "get_answer_agent", lambda: FakeAnswerAgent())
    response = make_client().post(
        "/api/v1/rag/query",
        headers={"X-Tenant-ID": "tenant-a"},
        json={"question": "What is RAG?", "top_k": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_count"] == 1
    assert body["citations"][0]["chunk_id"] == "chunk-1"
    assert "chunk-1" in body["answer"]


def test_upload_endpoint_calls_ingestion_service(monkeypatch):
    monkeypatch.setattr(rag_api, "get_rag_service", lambda: FakeService())
    response = make_client().post(
        "/api/v1/rag/documents",
        headers={"X-Tenant-ID": "tenant-a"},
        files={"file": ("guide.pdf", b"%PDF-test", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["chunk_count"] == 1


def test_upload_endpoint_rejects_non_pdf(monkeypatch):
    monkeypatch.setattr(rag_api, "get_rag_service", lambda: FakeService())
    response = make_client().post(
        "/api/v1/rag/documents",
        files={"file": ("guide.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("endpoint", ["query", "documents"])
def test_azure_mode_rejects_untrusted_tenant_header(monkeypatch, endpoint):
    monkeypatch.setattr(rag_api.settings, "rag_backend", "azure")

    def unexpected_service_call():
        pytest.fail("Untrusted tenant requests must not access the RAG service.")

    monkeypatch.setattr(rag_api, "get_rag_service", unexpected_service_call)
    with make_client() as client:
        if endpoint == "query":
            response = client.post(
                "/api/v1/rag/query",
                headers={"X-Tenant-ID": "tenant-a"},
                json={"question": "What is RAG?", "top_k": 2},
            )
        else:
            response = client.post(
                "/api/v1/rag/documents",
                headers={"X-Tenant-ID": "tenant-a"},
                files={"file": ("guide.pdf", b"%PDF-test", "application/pdf")},
            )
    assert response.status_code == 503
    assert "Microsoft Entra ID middleware" in response.json()["detail"]
