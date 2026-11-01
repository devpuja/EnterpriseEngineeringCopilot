import math
from time import perf_counter
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.rag_service import DeterministicEvidenceValidator, EvidenceValidationResult
from app.api.schemas import RAGCitationReference, RAGSource


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    query: str
    judgments: dict[str, int] | None = None
    retrieved_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_labels(self):
        if self.judgments is not None and any(
            grade < 0 or grade > 3 for grade in self.judgments.values()
        ):
            raise ValueError("Relevance grades must be 0-3.")
        if len(self.retrieved_ids) != len(set(self.retrieved_ids)):
            raise ValueError("Ranked retrieval IDs must be unique.")
        return self


class RetrievalEvaluation(BaseModel):
    case_id: str
    query: str
    retrieved_ids: list[str]
    judgments: dict[str, int] | None
    judgments_available: bool
    hit_rate: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    mrr: float | None = None
    ndcg: float | None = None
    duration_ms: float | None = None
    explanation: str


def evaluate_retrieval(
    case: RetrievalCase,
    retrieve: Callable[[str], list[str]] | None = None,
) -> RetrievalEvaluation:
    started = perf_counter()
    if retrieve is not None:
        case = RetrievalCase.model_validate({
            **case.model_dump(), "retrieved_ids": retrieve(case.query),
        })
    base = {
        "case_id": case.case_id, "query": case.query,
        "retrieved_ids": case.retrieved_ids, "judgments": case.judgments,
        "judgments_available": case.judgments is not None,
        "duration_ms": (perf_counter() - started) * 1000 if retrieve else None,
    }
    if case.judgments is None:
        return RetrievalEvaluation(**base, explanation="No ground-truth relevance labels; metrics unavailable.")
    relevant = {identifier for identifier, grade in case.judgments.items() if grade > 0}
    # Unjudged hits cannot safely be treated as irrelevant.
    if any(identifier not in case.judgments for identifier in case.retrieved_ids):
        return RetrievalEvaluation(**base, explanation="Some retrieved IDs are unjudged; metrics unavailable.")
    hits = [identifier for identifier in case.retrieved_ids if identifier in relevant]
    precision = len(hits) / len(case.retrieved_ids) if case.retrieved_ids else 0
    if not relevant:
        return RetrievalEvaluation(**base, context_precision=precision,
                                   explanation="No relevant ground-truth items; recall, MRR and NDCG undefined.")
    ranks = [index + 1 for index, identifier in enumerate(case.retrieved_ids) if identifier in relevant]
    dcg = sum((2 ** case.judgments[identifier] - 1) / math.log2(index + 2)
              for index, identifier in enumerate(case.retrieved_ids))
    ideal = sorted(case.judgments.values(), reverse=True)[:len(case.retrieved_ids)]
    idcg = sum((2 ** grade - 1) / math.log2(index + 2) for index, grade in enumerate(ideal))
    return RetrievalEvaluation(
        **base, hit_rate=float(bool(hits)), context_precision=precision,
        context_recall=len(hits) / len(relevant),
        mrr=1 / ranks[0] if ranks else 0,
        ndcg=dcg / idcg if idcg else 0,
        explanation="Metrics use explicit graded judgments; precision/recall use grade > 0.",
    )


def evaluate_grounding(
    answer: str, citations: list[RAGCitationReference], context: str,
    sources: list[RAGSource],
    chunks: dict[tuple[str, str, int, int | None], str],
) -> EvidenceValidationResult:
    return DeterministicEvidenceValidator().validate(
        answer, citations, context, sources, chunks,
    )
