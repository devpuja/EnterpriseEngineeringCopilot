from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.models import Criterion, EvaluationCase, EvaluationDataset
from app.evaluation.runner import run_evaluation


@pytest.mark.asyncio
async def test_versioned_dataset_repeatability_and_serialization():
    dataset = EvaluationDataset.model_validate_json(
        (Path(__file__).parent / "fixtures" / "genaiops" / "responses-v1.json").read_text()
    )
    first = await run_evaluation(dataset)
    second = await run_evaluation(dataset)
    assert first.passed == second.passed == 3
    assert [item.metrics for item in first.results] == [item.metrics for item in second.results]
    assert first.run_id != second.run_id
    assert '"dataset":' in first.model_dump_json()


@pytest.mark.asyncio
async def test_missing_reference_failures_and_executor_error():
    cases = [
        EvaluationCase(case_id="missing", output="answer", criteria=[Criterion(metric="normalized_match")]),
        EvaluationCase(case_id="schema", output={}, criteria=[Criterion(metric="schema", schema_name="architecture")]),
        EvaluationCase(case_id="source", output={"sources": ["invented"]}, valid_sources=["real"],
                       criteria=[Criterion(metric="sources")]),
    ]
    dataset = EvaluationDataset(name="failures", version="1", cases=cases)
    run = await run_evaluation(dataset)
    assert run.not_applicable == 1 and run.failed == 2
    async def fail(case):
        raise TimeoutError("private provider prompt")
    run = await run_evaluation(dataset, fail)
    assert run.errors == 3
    assert "private provider" not in run.model_dump_json()


def test_dataset_validation():
    case = EvaluationCase(case_id="duplicate", criteria=[Criterion(metric="normalized_match")])
    with pytest.raises(ValidationError):
        EvaluationDataset(name="test", version="1", cases=[case, case])
    with pytest.raises(ValidationError):
        Criterion(metric="invented_judge")
