import logging
from time import perf_counter
from typing import Awaitable, Callable

from pydantic import JsonValue

from app.evaluation.metrics import evaluate_metric
from app.evaluation.models import CaseResult, EvaluationCase, EvaluationDataset, EvaluationRun, MetricResult
from app.observability.metrics import operational_store
from app.observability.telemetry import observed


logger = logging.getLogger(__name__)


@observed("evaluation.run")
async def run_evaluation(
    dataset: EvaluationDataset,
    execute: Callable[[EvaluationCase], Awaitable[JsonValue]] | None = None,
) -> EvaluationRun:
    started = perf_counter()
    cases = []
    for case in dataset.cases:
        case_started = perf_counter()
        try:
            actual = case
            if execute is not None:
                output = await execute(case)
                actual = EvaluationCase.model_validate({
                    **case.model_dump(), "output": output,
                })
            metrics = [evaluate_metric(actual, criterion) for criterion in actual.criteria]
            statuses = {item.status for item in metrics}
            status = (
                "error" if "error" in statuses else "failed" if "failed" in statuses
                else "passed" if "passed" in statuses else "not_applicable"
            )
        except Exception as exc:
            logger.warning("event=evaluation_case_failed error_type=%s", type(exc).__name__)
            status = "error"
            metrics = [MetricResult(
                metric="execution", status="error", category=type(exc).__name__,
                explanation="Evaluation execution failed; content omitted.",
            )]
        cases.append(CaseResult(
            case_id=case.case_id, status=status, metrics=metrics,
            duration_ms=(perf_counter() - case_started) * 1000,
        ))
    run = EvaluationRun(
        dataset=dataset.name, version=dataset.version, results=cases,
        passed=sum(item.status == "passed" for item in cases),
        failed=sum(item.status == "failed" for item in cases),
        errors=sum(item.status == "error" for item in cases),
        not_applicable=sum(item.status == "not_applicable" for item in cases),
        duration_ms=(perf_counter() - started) * 1000,
    )
    operational_store.record("evaluation", summary=run.model_dump(mode="json"))
    return run
