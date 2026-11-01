from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.observability.metrics import operational_store
from app.observability.models import (
    EvaluationObservation, OperationObservation, QualityObservation,
    RetryObservation, UsageObservation,
)
from app.security import Role, UserPrincipal, require_roles


router = APIRouter(prefix="/api/v1/operations", tags=["GenAIOps"])


class OperationSummary(BaseModel):
    operation: str
    samples: int
    failures: int
    mean_duration_ms: float
    max_duration_ms: float


class UsageSummary(BaseModel):
    provider: str
    model: str
    calls: int
    unavailable_usage_calls: int
    reported_input_tokens: int
    reported_output_tokens: int
    unavailable_cost_calls: int
    estimated_cost_subtotals: dict[str, Decimal]


class QualityFailureSummary(BaseModel):
    gate: str
    category: str | None
    blocking: bool
    count: int


class OperationsSummary(BaseModel):
    minutes: int
    scope: str = "current_owner"
    retention: str = "Last 1000 observations across this process; incomplete after eviction/restart."
    operations: list[OperationSummary]
    usage: list[UsageSummary]
    retries: int
    evaluation_runs: int
    evaluation_failures: int
    quality_failures: int
    blocking_quality_failures: int = 0
    advisory_quality_failures: int = 0
    quality_failure_details: list[QualityFailureSummary] = Field(default_factory=list)


@router.get("/summary", response_model=OperationsSummary)
def get_operations_summary(
    minutes: int = Query(default=60, ge=1, le=1440),
    principal: UserPrincipal = Depends(require_roles(*Role)),
) -> OperationsSummary:
    records = operational_store.records(principal.owner_id, minutes)
    operation_rows: dict[str, list[OperationObservation]] = defaultdict(list)
    usage_rows: dict[tuple[str, str], list[UsageObservation]] = defaultdict(list)
    for row in records:
        if isinstance(row, OperationObservation):
            operation_rows[row.operation].append(row)
        elif isinstance(row, UsageObservation):
            usage_rows[(row.provider, row.model)].append(row)
    operations: list[OperationSummary] = []
    for name, rows in sorted(operation_rows.items()):
        durations = [row.duration_ms for row in rows]
        operations.append(OperationSummary(
            operation=name, samples=len(rows),
            failures=sum(row.outcome == "failed" for row in rows),
            mean_duration_ms=sum(durations) / len(durations),
            max_duration_ms=max(durations),
        ))
    usage: list[UsageSummary] = []
    for (provider, model), calls in sorted(usage_rows.items()):
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for row in calls:
            cost = row.cost
            if cost.status == "estimated" and cost.amount is not None and cost.currency is not None:
                totals[cost.currency] += cost.amount
        usage.append(UsageSummary(
            provider=provider, model=model, calls=len(calls),
            unavailable_usage_calls=sum(row.usage.source == "unavailable" for row in calls),
            reported_input_tokens=sum(row.usage.input_tokens or 0 for row in calls),
            reported_output_tokens=sum(row.usage.output_tokens or 0 for row in calls),
            unavailable_cost_calls=sum(row.cost.status == "unavailable" for row in calls),
            estimated_cost_subtotals=dict(totals),
        ))
    evaluations = [row.summary for row in records if isinstance(row, EvaluationObservation)]
    quality_failures = [
        row.summary for row in records
        if isinstance(row, QualityObservation) and row.summary.status == "failed"
    ]
    quality_counts: dict[tuple[str, str | None, bool], int] = defaultdict(int)
    for failure in quality_failures:
        quality_counts[(failure.gate, failure.category, failure.hard)] += 1
    return OperationsSummary(
        minutes=minutes, operations=operations, usage=usage,
        retries=sum(isinstance(row, RetryObservation) for row in records),
        evaluation_runs=len(evaluations),
        evaluation_failures=sum(run.failed + run.errors for run in evaluations),
        quality_failures=len(quality_failures),
        blocking_quality_failures=sum(failure.hard for failure in quality_failures),
        advisory_quality_failures=sum(not failure.hard for failure in quality_failures),
        quality_failure_details=[
            QualityFailureSummary(gate=gate, category=category, blocking=hard, count=count)
            for (gate, category, hard), count in sorted(
                quality_counts.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2]),
            )
        ],
    )
