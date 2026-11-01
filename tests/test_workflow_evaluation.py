from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.evaluation.models import Criterion, EvaluationCase, EvaluationDataset
from app.evaluation.workflow import evaluate_stages, evaluate_target
from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.analysis.repository_analyzer import RepositoryAnalyzer
from app.repository.exceptions import RepositoryNotFoundError
from app.repository.reporting.models import ReportConfiguration, ReportFormat
from app.repository.reporting.validation import ReportValidationError
from app.repository.workspace_manager import WorkspaceManager
from app.services.repository_report_service import RepositoryReportService, ReportExportFailedError


@pytest.mark.asyncio
async def test_synthetic_workflow_regression_dataset(tmp_path, monkeypatch):
    dataset = EvaluationDataset.model_validate_json(
        (Path(__file__).parent / "fixtures" / "genaiops" / "workflows-v1.json").read_text()
    )
    required = ["retrieve", "analyze", "visualize", "synthesize", "review", "generate"]

    async def execute(case):
        scenario = case.input
        if scenario == "provider-timeout":
            from app.agents.requirements_agent import RequirementsAnalysisAgent
            class TimeoutAgent:
                async def run(self, *args, **kwargs):
                    raise TimeoutError("synthetic timeout")
            try:
                await RequirementsAnalysisAgent(TimeoutAgent()).analyze("Build an API.")
            except TimeoutError:
                return "TimeoutError"
        if scenario == "invalid-agent-output":
            from app.agents.requirements_agent import RequirementsAnalysisAgent
            class InvalidAgent:
                async def run(self, *args, **kwargs):
                    return SimpleNamespace(value={}, text="{}")
            try:
                await RequirementsAnalysisAgent(InvalidAgent()).analyze("Build an API.")
            except ValueError:
                return "invalid_schema"
        root = tmp_path / case.case_id
        root.mkdir()
        if scenario == "unsupported":
            (root / "app.unknown").write_text("synthetic unsupported code")
        elif scenario != "incomplete-evidence":
            (root / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
            if scenario == "complex":
                for index in range(20):
                    (root / f"module{index}.py").write_text("import asyncio\n")
            if scenario == "ambiguous-dependencies":
                (root / "requirements.txt").write_text("unknown-private-package\n")
        workspace = WorkspaceManager(tmp_path / f"workspace-{case.case_id}")
        service = RepositoryReportService(
            workspace_manager=workspace,
            local_adapter=LocalRepositoryAdapter(workspace, allowed_roots=[str(tmp_path)]),
            analyzer=RepositoryAnalyzer(workspace),
            output_directory=tmp_path / f"exports-{case.case_id}",
        )
        stages = []
        for target, method, name in (
            (service.local_adapter, "retrieve", "retrieve"),
            (service.analyzer, "aanalyze", "analyze"),
            (service.visualizer, "visualize", "visualize"),
            (service.synthesizer, "synthesize", "synthesize"),
            (service.reviewer, "review", "review"),
            (service.report_generator, "generate", "generate"),
        ):
            original = getattr(target, method)
            if method in {"retrieve", "aanalyze"}:
                async def async_record(*args, _original=original, _name=name, **kwargs):
                    stages.append(_name)
                    if scenario == "inaccessible" and _name == "retrieve":
                        raise RepositoryNotFoundError()
                    return await _original(*args, **kwargs)
                monkeypatch.setattr(target, method, async_record)
            else:
                def record(*args, _original=original, _name=name, **kwargs):
                    stages.append(_name)
                    return _original(*args, **kwargs)
                monkeypatch.setattr(target, method, record)
        if scenario == "partial-stage":
            monkeypatch.setattr(service.analyzer.api_analyzer, "analyze",
                                lambda *args: (_ for _ in ()).throw(RuntimeError()))
        try:
            analysis, report = await service.create_report(
                "local", str(root), None, ReportConfiguration(), owner_id="synthetic-owner"
            )
        except RepositoryNotFoundError:
            assert stages == ["retrieve"]
            return "RepositoryNotFoundError"
        assert evaluate_stages(stages, required).status == "passed"
        assert not list(workspace.workspace_root.iterdir())
        if scenario == "partial-stage":
            assert analysis.analysis_warnings
            return "partial"
        if scenario == "invalid-source":
            from app.repository.reporting.validation import validate_report
            report.report_metadata.options["analysis_id"] = str(uuid4())
            try:
                validate_report(report)
            except ReportValidationError:
                return "ReportValidationError"
        if scenario == "export-failure":
            class FailedExporter:
                def export(self, *args):
                    return SimpleNamespace(export_status="failed")
            monkeypatch.setattr(service, "_exporter", lambda *args: FailedExporter())
            try:
                await service.export_report(report.report_id, ReportFormat.markdown, "synthetic-owner")
            except ReportExportFailedError:
                return "ReportExportFailedError"
        for format in ReportFormat:
            exported, artifacts = await service.export_report(report.report_id, format, "synthetic-owner")
            assert exported.export_status == "completed"
            assert artifacts
        return "completed"

    run = await evaluate_target(dataset, execute)
    assert run.passed == 12, run.model_dump_json()
    assert run.failed == run.errors == 0


@pytest.mark.asyncio
async def test_independent_agents_are_evaluated_through_real_parsers():
    from app.agents.requirements_agent import RequirementsAnalysisAgent
    from app.agents.architecture_review_agent import ArchitectureReviewAgent
    from app.agents.architecture_agent import ArchitectureAgent
    from tests.test_architecture_api import valid_architecture_response

    response = valid_architecture_response()
    requirements = response.requirements_analysis
    class Fake:
        def __init__(self, value):
            self.value = value
        async def run(self, *args, **kwargs):
            return SimpleNamespace(value=self.value)
    architecture_agent = ArchitectureAgent()
    architecture_agent._agent = Fake(response)
    targets = {
        "requirements": lambda: RequirementsAnalysisAgent(Fake(requirements)).analyze("Build an API."),
        "architecture": lambda: architecture_agent.design("Build an API.", "openai"),
        "review": lambda: ArchitectureReviewAgent(Fake({
            "summary": "Synthetic review", "findings": [], "approval_recommendation": "approve",
        })).review(response),
    }
    for name, target in targets.items():
        case = EvaluationCase(case_id=name, criteria=[Criterion(metric="schema", schema_name=name)])
        async def execute(case):
            return (await target()).model_dump(mode="json")
        run = await evaluate_target(EvaluationDataset(name=name, version="1", cases=[case]), execute,
                                    provider="synthetic", model="fixture")
        assert run.passed == 1


def test_workflow_stage_gate_rejects_missing_review():
    assert evaluate_stages(["requirements", "design"], ["requirements", "design", "review"]).status == "failed"
