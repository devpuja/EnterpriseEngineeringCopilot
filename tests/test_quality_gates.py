from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError

from app.evaluation.quality import quality_gate, validation_gate
from app.services.embedding_service import EmbeddingServiceError, OpenAIEmbeddingService


def test_advisory_and_hard_gate_outcomes():
    assert quality_gate("fixture", True, hard=True, category="invalid").status == "passed"
    assert quality_gate("fixture", False, hard=False, category="weak_evidence").status == "failed"
    with pytest.raises(ValueError, match="rejected"):
        quality_gate("fixture", False, hard=True, category="weak_evidence")
    with pytest.raises(ValueError, match="original"):
        with validation_gate("fixture"):
            raise ValueError("original contract")


def test_embedding_retry_limit_and_permanent_classification(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service.time, "sleep", lambda seconds: None)
    provider = OpenAIEmbeddingService("synthetic-key", model="synthetic", max_retries=2)
    calls = []
    def transient(**kwargs):
        calls.append(1)
        raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    provider._client = SimpleNamespace(embeddings=SimpleNamespace(create=transient))
    with pytest.raises(EmbeddingServiceError):
        provider.embed(["synthetic content"])
    assert len(calls) == 3
    calls.clear()
    def permanent(**kwargs):
        calls.append(1)
        raise ValueError("bad provider configuration")
    provider._client = SimpleNamespace(embeddings=SimpleNamespace(create=permanent))
    with pytest.raises(EmbeddingServiceError):
        provider.embed(["synthetic content"])
    assert len(calls) == 1
