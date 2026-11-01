from typing import Awaitable, Callable

from pydantic import JsonValue

from app.evaluation.metrics import result
from app.evaluation.models import EvaluationCase, EvaluationDataset, EvaluationRun, MetricResult
from app.evaluation.runner import run_evaluation


async def evaluate_target(
    dataset: EvaluationDataset,
    execute: Callable[[EvaluationCase], Awaitable[JsonValue]],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> EvaluationRun:
    """Evaluate an injected agent/workflow; fixtures never imply live model quality."""
    run = await run_evaluation(dataset, execute)
    run.provider = provider
    run.model = model
    return run


def evaluate_stages(actual: list[str], required: list[str]) -> MetricResult:
    return result(
        "workflow_stages", actual == required,
        "Required stages and ordering compared with observed execution.",
        "workflow_incomplete",
    )
