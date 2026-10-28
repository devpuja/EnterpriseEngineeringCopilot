import pytest

from app.api.schemas import IndexedDocument, RAGCitationReference, RAGSource
from app.services.document_ingestion import (
    DocumentChunk,
    DocumentIngestionError,
    ingest_document,
    split_text,
    stable_document_id,
    stable_chunk_id,
)
from app.services.document_repository import DocumentRepository
from app.services.embedding_service import DeterministicEmbeddingService, OpenAIEmbeddingService, EmbeddingServiceError
from app.services.vector_store import ChromaVectorStore
from app.services.rag_service import (
    DeterministicEvidenceValidator,
    EvidenceValidationResult,
    RAGService,
)


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


PREFERRED_QUALIFICATIONS = """
Preferred Qualifications
1. Experience with LangChain, Semantic Kernel, or Haystack for RAG implementation.
2. Familiarity with MLOps, model registries, and monitoring tools.
3. Strong understanding of data privacy, AI governance, and responsible AI practices.
4. Prior experience deploying AI systems in regulated or security-sensitive industries (e.g., healthcare, finance, government).
5. Excellent communication skills and experience working cross-functionally with engineering, product, and leadership teams.
""".strip()


def test_heading_section_spanning_chunks_is_assembled_without_truncation(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "section_collection")
    repository = DocumentRepository(str(tmp_path / "metadata.db"))
    document_id = "preferred-doc"
    chunks = [
        DocumentChunk(stable_chunk_id(document_id, 0), document_id, "AI Architect.txt", 0,
                      "Required Qualifications\n- Python experience\nPreferred Qualifications\n"
                      "1. Experience with LangChain, Semantic Kernel, or Haystack for RAG implementation.\n"
                      "2. Familiarity with MLOps, model registries, and monitoring tools.", 1),
        DocumentChunk(stable_chunk_id(document_id, 1), document_id, "AI Architect.txt", 1,
                      "3. Strong understanding of data privacy, AI governance, and responsible AI practices.\n"
                      "4. Prior experience deploying AI systems in regulated or security-sensitive industries.\n"
                      "5. Excellent communication skills and experience working cross-functionally with engineering, product, and leadership teams.", 1),
    ]
    embeddings = provider.embed([chunk.text for chunk in chunks])
    store.replace_document(chunks, embeddings)

    service = RAGService(provider, store, repository, str(tmp_path / "docs"), 100, 20, 5, 12000)
    expanded = store.get_neighbor_chunks(
        [{"metadata": {"document_id": document_id, "chunk_index": 0}, "text": chunks[0].text}],
        radius=1,
    )
    context, sources = service._assemble_context(expanded)

    assert "LangChain, Semantic Kernel, or Haystack" in context
    assert "MLOps, model registries" in context
    assert "data privacy, AI governance" in context
    assert "regulated or security-sensitive industries" in context
    assert "cross-functionally with engineering, product, and leadership teams" in context
    assert [source.chunk_index for source in sources] == [0, 1]
    assert all(source.filename == "AI Architect.txt" for source in sources)
    assert all(source.page_number == 1 for source in sources)


def test_neighbor_expansion_does_not_mix_documents(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "multi_document_collection")
    chunks_a = [DocumentChunk(stable_chunk_id("doc-a", 0), "doc-a", "A.txt", 0, "A chunk zero", None),
                DocumentChunk(stable_chunk_id("doc-a", 1), "doc-a", "A.txt", 1, "A chunk one", None)]
    chunks_b = [DocumentChunk(stable_chunk_id("doc-b", 0), "doc-b", "B.txt", 0, "B chunk zero", None)]
    store.replace_document(chunks_a, provider.embed([chunk.text for chunk in chunks_a]))
    store.replace_document(chunks_b, provider.embed([chunk.text for chunk in chunks_b]))

    expanded = store.get_neighbor_chunks(
        [{"metadata": {"document_id": "doc-a", "chunk_index": 0}, "text": "A chunk zero"}],
        radius=1,
    )
    assert {item["metadata"]["document_id"] for item in expanded} == {"doc-a"}
    assert {item["metadata"]["chunk_index"] for item in expanded} == {0, 1}


@pytest.mark.asyncio
async def test_absent_section_is_not_fabricated(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "absent_collection")
    repository = DocumentRepository(str(tmp_path / "metadata.db"))

    class FakeAnswerAgent:
        async def run(self, prompt, options=None):
            from types import SimpleNamespace
            return SimpleNamespace(value=None, text='{"answer":"The indexed documents do not provide enough information to answer this question.","grounded":false}')

    class RealizedStore:
        pass

    service = RAGService(provider, store, repository, str(tmp_path / "docs"), 100, 20, 5, 12000, answer_agent=FakeAnswerAgent())
    answer = await service.answer("Preferred Qualifications")
    assert answer.grounded is False
    assert answer.sources == []


def test_sentence_spanning_chunk_boundaries_uses_overlap():
    text = "Lead context. " * 7 + "Preferred Qualifications span the chunk boundary without losing meaning."
    chunks = split_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0][-20:] == chunks[1][:20]
    reconstructed = chunks[0] + chunks[1][20:]
    assert "Preferred Qualifications span the chunk boundary without losing meaning." in reconstructed


def test_source_excerpt_is_preview_and_reports_truncation(tmp_path):
    service = RAGService(
        DeterministicEmbeddingService(),
        ChromaVectorStore(str(tmp_path / "chroma"), "excerpt_collection"),
        DocumentRepository(str(tmp_path / "metadata.db")),
        str(tmp_path / "docs"), 100, 20, 5, 12000,
        source_excerpt_char_limit=40,
    )
    full_text = "A complete stored chunk with more text than the configured source preview limit."
    context, sources = service._assemble_context([{
        "text": full_text,
        "metadata": {
            "document_id": "doc-1",
            "filename": "guide.txt",
            "chunk_index": 0,
            "page_number": 2,
        },
    }])
    assert full_text in context
    assert sources[0].excerpt == full_text[:40]
    assert sources[0].excerpt_truncated is True


def test_context_budget_skips_complete_chunks_without_mid_chunk_truncation(tmp_path):
    service = RAGService(
        DeterministicEmbeddingService(),
        ChromaVectorStore(str(tmp_path / "chroma"), "budget_collection"),
        DocumentRepository(str(tmp_path / "metadata.db")),
        str(tmp_path / "docs"), 100, 20, 5, 90,
    )
    context, sources = service._assemble_context([
        {"text": "Short first chunk", "metadata": {"document_id": "doc", "filename": "a.txt", "chunk_index": 0, "page_number": None}},
        {"text": "This second chunk is deliberately much too long for the tiny context budget", "metadata": {"document_id": "doc", "filename": "a.txt", "chunk_index": 1, "page_number": None}},
    ])
    assert "Short first chunk" in context
    assert "deliberately much too long" not in context
    assert [source.chunk_index for source in sources] == [0]


def test_deterministic_evidence_validation_supported_answer():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=2, page_number=1,
                       excerpt="The office is in London.")
    citation = RAGCitationReference(document_id="doc-1", filename="guide.txt", chunk_index=2, page_number=1)
    result = DeterministicEvidenceValidator().validate(
        "The office is in London.", [citation], "[Source 1 | guide.txt | page 1 | chunk 2]\nThe office is in London.", [source],
        included_chunks={("doc-1", "guide.txt", 2, 1): "The office is in London."},
    )
    assert result.status == "verified"


def test_deterministic_evidence_validation_rejects_unsupported_claim_and_bad_citation():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=2, page_number=1,
                       excerpt="The office is in London.")
    valid_citation = RAGCitationReference(document_id="doc-1", filename="guide.txt", chunk_index=2, page_number=1)
    invalid_citation = RAGCitationReference(document_id="other", filename="other.txt", chunk_index=99, page_number=None)
    validator = DeterministicEvidenceValidator()

    chunks = {("doc-1", "guide.txt", 2, 1): "The office is in London."}
    unsupported = validator.validate(
        "The office is in London. The salary is five hundred thousand dollars.",
        [valid_citation], "The office is in London.", [source], included_chunks=chunks
    )
    assert unsupported.status == "unverified"
    assert "salary" in unsupported.unsupported_claims[0].lower()

    invalid = validator.validate(
        "The office is in London.", [invalid_citation], "The office is in London.", [source], included_chunks=chunks
    )
    assert invalid.status == "unverified"
    assert invalid.invalid_citations


def test_numeric_contradiction_is_not_verified():
    source = RAGSource(document_id="doc-1", filename="roles.txt", chunk_index=0,
                       page_number=3, excerpt="Candidates need 10+ years of experience.")
    citation = RAGCitationReference(document_id="doc-1", filename="roles.txt", chunk_index=0, page_number=3)
    result = DeterministicEvidenceValidator().validate(
        "Candidates need 20+ years of experience.",
        [citation],
        "[Source 1 | roles.txt | page 3 | chunk 0]\nCandidates need 10+ years of experience.",
        [source],
        included_chunks={("doc-1", "roles.txt", 0, 3): "Candidates need 10+ years of experience."},
    )
    assert result.status == "unverified"
    assert any("20+ years" in claim or "20" in claim for claim in result.unsupported_claims)


def test_unsupported_named_entity_is_not_verified():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=0,
                       excerpt="Ada works remotely on the engineering team.")
    citation = RAGCitationReference(document_id="doc-1", filename="guide.txt", chunk_index=0)
    result = DeterministicEvidenceValidator().validate(
        "Ada Lovelace works remotely on the engineering team.",
        [citation],
        "Ada works remotely on the engineering team.",
        [source],
        included_chunks={("doc-1", "guide.txt", 0, None): "Ada works remotely on the engineering team."},
    )
    assert result.status == "unverified"


def test_heavy_word_overlap_is_not_treated_as_entailment():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=0,
                       excerpt="The engineering team uses Python for backend API work.")
    citation = RAGCitationReference(document_id="doc-1", filename="guide.txt", chunk_index=0)
    result = DeterministicEvidenceValidator().validate(
        "The engineering team uses Java for backend API work.",
        [citation],
        "The engineering team uses Python for backend API work.",
        [source],
        included_chunks={("doc-1", "guide.txt", 0, None): "The engineering team uses Python for backend API work."},
    )
    assert result.status == "unverified"


def test_direct_quote_with_normalization_difference_is_supported():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=0,
                       excerpt='The policy says “secure-by-default”.')
    citation = RAGCitationReference(document_id="doc-1", filename="guide.txt", chunk_index=0)
    result = DeterministicEvidenceValidator().validate(
        'The policy says “secure-by-default”.',
        [citation],
        "The policy says secure-by-default.",
        [source],
        included_chunks={("doc-1", "guide.txt", 0, None): "The policy says secure-by-default."},
    )
    assert result.status == "verified"


def test_missing_citation_is_not_verified():
    source = RAGSource(document_id="doc-1", filename="guide.txt", chunk_index=0, excerpt="The office is remote.")
    result = DeterministicEvidenceValidator().validate(
        "The office is remote.", [], "The office is remote.", [source]
    )
    assert result.status == "unverified"


@pytest.mark.asyncio
async def test_model_grounded_true_is_not_independent_verification(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "model_grounded_collection")
    repository = DocumentRepository(str(tmp_path / "metadata.db"))
    chunks = [DocumentChunk(stable_chunk_id("doc-1", 0), "doc-1", "guide.txt", 0, "The office is remote.", 1)]
    store.replace_document(chunks, provider.embed([chunks[0].text]))

    class FakeAnswerAgent:
        async def run(self, prompt, options=None):
            from types import SimpleNamespace
            return SimpleNamespace(value=None, text='''{"answer":"The office is remote and the salary is one million dollars.","grounded":true,"citations":[{"document_id":"doc-1","filename":"guide.txt","chunk_index":0,"page_number":1}]}''')

    service = RAGService(provider, store, repository, str(tmp_path / "docs"), 100, 20, 5, 12000,
                         answer_agent=FakeAnswerAgent())
    answer = await service.answer("What is the office location and salary?")
    assert answer.model_grounded is True
    assert answer.verification_status == "unverified"
    assert answer.grounded is False


@pytest.mark.asyncio
async def test_verification_exception_is_inconclusive(tmp_path):
    provider = DeterministicEmbeddingService()
    store = ChromaVectorStore(str(tmp_path / "chroma"), "verification_failure_collection")
    repository = DocumentRepository(str(tmp_path / "metadata.db"))
    chunks = [DocumentChunk(stable_chunk_id("doc-1", 0), "doc-1", "guide.txt", 0, "The office is remote.", 1)]
    store.replace_document(chunks, provider.embed([chunks[0].text]))

    class FakeAnswerAgent:
        async def run(self, prompt, options=None):
            from types import SimpleNamespace
            return SimpleNamespace(value=None, text='''{"answer":"The office is remote.","grounded":true,"citations":[{"document_id":"doc-1","filename":"guide.txt","chunk_index":0,"page_number":1}]}''')

    class FailingValidator:
        def validate(self, **kwargs):
            raise RuntimeError("verification unavailable")

    service = RAGService(provider, store, repository, str(tmp_path / "docs"), 100, 20, 5, 12000,
                         answer_agent=FakeAnswerAgent(), evidence_validator=FailingValidator())
    answer = await service.answer("Where is the office?")
    assert answer.grounded is False
    assert answer.verification_status == "inconclusive"
    assert answer.model_grounded is True
