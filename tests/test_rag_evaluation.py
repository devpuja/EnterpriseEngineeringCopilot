import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.rag import RetrievalCase, evaluate_grounding, evaluate_retrieval
from app.api.schemas import RAGCitationReference, RAGSource


def test_exact_ranking_metrics():
    case = RetrievalCase(case_id="rank", query="synthetic", judgments={"a":3,"b":0,"c":2},
                         retrieved_ids=["b","a"])
    result = evaluate_retrieval(case)
    assert result.hit_rate == 1
    assert result.context_precision == .5
    assert result.context_recall == .5
    assert result.mrr == .5
    assert result.ndcg == pytest.approx(0.4966392596877323)


def test_versioned_dataset_and_undefined_metrics():
    values = json.loads((Path(__file__).parent / "fixtures" / "genaiops" / "rag-v1.json").read_text())
    results = {case["case_id"]: evaluate_retrieval(RetrievalCase.model_validate(case)) for case in values}
    assert len(results) == 9
    assert results["obvious"].ndcg == 1
    assert results["partial"].mrr == .5
    assert results["missing-metadata"].ndcg is None
    assert results["no-relevant"].context_recall is None
    assert results["insufficient"].hit_rate == 0
    unknown = evaluate_retrieval(RetrievalCase(case_id="unknown", query="q", judgments={"a":1}, retrieved_ids=["b"]))
    assert unknown.context_precision is None
    with pytest.raises(ValidationError):
        RetrievalCase(case_id="duplicate", query="q", retrieved_ids=["a", "a"])


def test_grounding_reuses_conservative_validator():
    source = RAGSource(document_id="doc", filename="synthetic.txt", chunk_index=0,
                       page_number=None, excerpt="API validates tokens.")
    citation = RAGCitationReference(document_id="doc", filename="synthetic.txt", chunk_index=0, page_number=None)
    key = ("doc", "synthetic.txt", 0, None)
    assert evaluate_grounding("API validates tokens.", [citation], "API validates tokens.",
                              [source], {key:"API validates tokens."}).status == "verified"
    assert evaluate_grounding("Database is encrypted.", [citation], "API validates tokens.",
                              [source], {key:"API validates tokens."}).status == "unverified"
    assert evaluate_grounding("Insufficient evidence.", [], "", [], {}).status == "inconclusive"


def test_retrieval_duration_uses_actual_execution():
    case = RetrievalCase(case_id="run", query="q", judgments={"a":1})
    result = evaluate_retrieval(case, lambda query: ["a"])
    assert result.duration_ms >= 0
    assert result.retrieved_ids == ["a"]
