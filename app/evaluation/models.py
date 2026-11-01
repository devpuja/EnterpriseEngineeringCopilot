from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal["normalized_match", "required_fields", "schema", "sources", "contains"]
    fields: list[str] = Field(default_factory=list)
    schema_name: Literal["requirements", "architecture", "review", "report", "rag"] | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=80)
    input: JsonValue = None
    output: JsonValue = None
    reference: JsonValue = None
    criteria: list[Criterion] = Field(min_length=1)
    valid_sources: list[str] | None = None


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Evaluation case IDs must be unique.")
        return self


class MetricResult(BaseModel):
    metric: str
    status: Literal["passed", "failed", "not_applicable", "error"]
    score: float | None = Field(default=None, ge=0, le=1)
    category: str | None = None
    explanation: str


class CaseResult(BaseModel):
    case_id: str
    status: Literal["passed", "failed", "not_applicable", "error"]
    metrics: list[MetricResult]
    duration_ms: float = Field(ge=0)


class EvaluationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset: str
    version: str
    evaluator: str = "deterministic-v1"
    results: list[CaseResult]
    passed: int
    failed: int
    errors: int
    not_applicable: int
    duration_ms: float
    provider: str | None = None
    model: str | None = None
