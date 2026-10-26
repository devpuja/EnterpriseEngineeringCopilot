import asyncio
from types import SimpleNamespace

from app.agents.rag_answer_agent import RagAnswerAgent
from app.rag.models import RetrievedChunk


class FakeAgent:
    def __init__(self, text="Answer [chunk-1]"):
        self.prompt = None
        self.text = text

    async def run(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(text=self.text)


def test_no_retrieval_evidence_abstains_without_calling_model():
    fake = FakeAgent()
    answerer = RagAnswerAgent(agent=fake)
    result = asyncio.run(answerer.answer("What is RAG?", []))
    assert "could not find supporting evidence" in result
    assert fake.prompt is None


def test_answer_prompt_contains_citations_and_marks_document_as_untrusted():
    fake = FakeAgent("RAG retrieves evidence [chunk-1].")
    answerer = RagAnswerAgent(agent=fake)
    chunks = [RetrievedChunk(
        chunk_id="chunk-1", document_id="doc-1", file_name="guide.pdf",
        version=1, chunk_index=0, content="RAG retrieves relevant evidence.", score=0.9,
    )]
    result = asyncio.run(answerer.answer("What does RAG do?", chunks))
    assert result == "RAG retrieves evidence [chunk-1]."
    assert "[chunk_id=chunk-1" in fake.prompt
    assert "untrusted source material" in fake.prompt
