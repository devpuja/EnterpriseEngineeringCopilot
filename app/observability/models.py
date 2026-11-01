from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.evaluation.models import EvaluationRun


class ModelPricing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=100)
    input_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    output_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    cached_input_per_million: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    version: str = Field(min_length=1, max_length=80)


class TokenUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    source: Literal["provider_reported", "unavailable"] = "provider_reported"

    @model_validator(mode="after")
    def validate_cached(self):
        if self.cached_input_tokens is not None and self.input_tokens is not None:
            if self.cached_input_tokens > self.input_tokens:
                raise ValueError("Cached input exceeds total input tokens.")
        return self


class CostEstimate(BaseModel):
    status: Literal["estimated", "unavailable"]
    amount: Decimal | None = None
    currency: str | None = None
    pricing_version: str | None = None


class QualityOutcome(BaseModel):
    gate: str
    status: Literal["passed", "failed"]
    hard: bool
    category: str | None = None


class ObservationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: str | None = None
    request_id: str | None = None
    workflow: str | None = None
    agent: str | None = None


class OperationObservation(ObservationBase):
    kind: Literal["operation"]
    operation: str
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    outcome: Literal["success", "failed"]


class UsageObservation(ObservationBase):
    kind: Literal["usage"]
    provider: str
    model: str
    usage: TokenUsage
    cost: CostEstimate


class RetryObservation(ObservationBase):
    kind: Literal["retry"]
    operation: str


class EvaluationObservation(ObservationBase):
    kind: Literal["evaluation"]
    summary: EvaluationRun


class QualityObservation(ObservationBase):
    kind: Literal["quality"]
    summary: QualityOutcome


Observation = Annotated[
    OperationObservation | UsageObservation | RetryObservation | EvaluationObservation | QualityObservation,
    Field(discriminator="kind"),
]
