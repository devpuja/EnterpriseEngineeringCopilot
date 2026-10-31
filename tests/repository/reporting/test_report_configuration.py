from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import repository_reports
from app.repository.reporting.identifiers import SECTION_ORDER, SUPPORTED_DIAGRAM_TYPES
from app.repository.reporting.exporters import (
    DOCXExporter, HTMLExporter, MarkdownExporter, PDFExporter,
)
from app.repository.reporting.models import ReportConfiguration
from app.repository.reporting.report_generator import ReportGenerator
from app.repository.reporting.validation import ReportValidationError, validate_report
from app.repository.review import ArchitectureReviewService
from app.repository.synthesis import ArchitectureSynthesizer
from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
from app.repository.visualization.models import DiagramType
from tests.repository.visualization.test_milestone3_visualization import analysis_fixture


@pytest.fixture
def milestone_results():
    analysis = analysis_fixture()
    analysis.source_type = "github"
    analysis.source_reference = "https://github.com/devpuja/Agents/tree/main/agent-project"
    visualization = ArchitectureVisualizer().visualize(analysis)
    synthesis = ArchitectureSynthesizer().synthesize(analysis, visualization)
    review = ArchitectureReviewService().review(synthesis, analysis)
    return analysis, visualization, synthesis, review


def generate_report(results, configuration):
    analysis, visualization, synthesis, review = results
    return ReportGenerator().generate(
        analysis, visualization, configuration, synthesis=synthesis, review=review
    )


@pytest.mark.parametrize("diagram_type", SUPPORTED_DIAGRAM_TYPES)
def test_every_supported_diagram_preserves_selection_and_references(milestone_results, diagram_type):
    report = generate_report(
        milestone_results, ReportConfiguration(selected_diagram_types=[diagram_type])
    )
    expected_ids = {
        item.diagram_id for item in milestone_results[1].diagrams
        if item.diagram_type.value == diagram_type
    }
    if diagram_type in {"component", "unified_architecture"}:
        expected_ids.add("unified_architecture")
    assert {item.diagram_id for item in report.diagrams} == expected_ids
    assert report.configuration.selected_diagram_types == [diagram_type]
    assert report.report_metadata.options["configuration"]["selected_diagram_types"] == [diagram_type]
    validate_report(report, require_marked=True)


@pytest.mark.parametrize("section_id", SECTION_ORDER)
def test_every_supported_section_preserves_selection(milestone_results, section_id):
    report = generate_report(
        milestone_results, ReportConfiguration(include_sections=[section_id])
    )
    assert {item.section_id for item in report.sections} == {
        section_id, "limitations", "evidence_references"
    }
    assert report.configuration.include_sections == [section_id]
    validate_report(report, require_marked=True)


def test_empty_arrays_and_combined_selection_remain_backward_compatible(milestone_results):
    report = generate_report(milestone_results, ReportConfiguration())
    assert [item.section_id for item in report.sections] == list(SECTION_ORDER)
    assert len(report.diagrams) == 8
    selected = generate_report(milestone_results, ReportConfiguration(
        selected_diagram_types=["api", "unified_architecture"],
        include_sections=["architecture_diagrams", "api_architecture"],
        exclude_sections=["limitations", "evidence_references"],
    ))
    assert [item.section_id for item in selected.sections] == [
        "architecture_diagrams", "api_architecture"
    ]
    assert {item.diagram_id for item in selected.diagrams} == {"api_architecture", "unified_architecture"}
    validate_report(selected, require_marked=True)


@pytest.mark.parametrize(("configuration", "message"), [
    ({"selected_diagram_types": ["unsupported"]}, "unsupported diagram types: unsupported"),
    ({"selected_diagram_types": ["API"]}, "unsupported diagram types: API"),
    ({"selected_diagram_types": ["system-context"]}, "unsupported diagram types: system-context"),
    ({"selected_diagram_types": ["api_architecture"]}, "unsupported diagram types: api_architecture"),
    ({"include_sections": ["architecture_summary"]}, "include_sections: unknown section IDs"),
    ({"exclude_sections": ["unsupported"]}, "exclude_sections: unknown section IDs"),
    ({"include_sections": ["cover"], "exclude_sections": ["cover"]}, "both included and excluded"),
    ({"include_sections": ["limitations"], "include_limitations": False}, "explicitly selected but disabled"),
    ({"include_sections": ["evidence_references"], "include_evidence": False}, "explicitly selected but disabled"),
])
def test_api_rejects_invalid_configuration_before_retrieval(monkeypatch, configuration, message, caplog):
    create_report = AsyncMock()
    monkeypatch.setattr(repository_reports.repository_report_service, "create_report", create_report)
    app = FastAPI()
    app.include_router(repository_reports.router)
    with TestClient(app) as client:
        response = client.post("/api/v1/repository-reports/analyses", json={
            "source_type": "github",
            "source_reference": "https://github.com/devpuja/Agents/tree/main/agent-project",
            "branch": "main",
            "configuration": configuration,
        })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "configuration"]
    assert message in response.json()["detail"][0]["msg"]
    assert "repository_report_configuration_rejected" in caplog.text
    create_report.assert_not_awaited()


def test_api_preserves_generation_validation_error(monkeypatch):
    create_report = AsyncMock(side_effect=ReportValidationError("sections: missing required section IDs api_architecture"))
    monkeypatch.setattr(repository_reports.repository_report_service, "create_report", create_report)
    app = FastAPI()
    app.include_router(repository_reports.router)
    with TestClient(app) as client:
        response = client.post("/api/v1/repository-reports/analyses", json={
            "source_type": "github", "source_reference": "https://github.com/devpuja/Agents",
        })
    assert response.status_code == 422
    assert response.json()["detail"] == "sections: missing required section IDs api_architecture"


def test_api_propagates_valid_combined_configuration(monkeypatch, milestone_results):
    async def create_report(source_type, source_reference, branch, configuration):
        assert source_type == "github"
        assert source_reference.endswith("/tree/main/agent-project")
        assert branch == "main"
        assert configuration.selected_diagram_types == ["api", "unified_architecture"]
        assert configuration.include_sections == ["architecture_diagrams", "api_architecture"]
        return milestone_results[0], generate_report(milestone_results, configuration)

    service = repository_reports.repository_report_service
    monkeypatch.setattr(service, "create_report", create_report)
    app = FastAPI()
    app.include_router(repository_reports.router)
    with TestClient(app) as client:
        response = client.post("/api/v1/repository-reports/analyses", json={
            "source_type": "github",
            "source_reference": "https://github.com/devpuja/Agents/tree/main/agent-project",
            "branch": "main",
            "configuration": {
                "selected_diagram_types": ["api", "unified_architecture"],
                "include_sections": ["architecture_diagrams", "api_architecture"],
            },
        })
    assert response.status_code == 201
    assert response.json()["report"]["section_ids"] == [
        "architecture_diagrams", "api_architecture", "limitations", "evidence_references"
    ]
    assert {item["diagram_id"] for item in response.json()["report"]["diagrams"]} == {
        "api_architecture", "unified_architecture"
    }


@pytest.mark.parametrize("exporter", [
    MarkdownExporter(), HTMLExporter(), PDFExporter(), DOCXExporter(),
])
def test_combined_selection_exports_all_formats(milestone_results, tmp_path, exporter):
    report = generate_report(milestone_results, ReportConfiguration(
        selected_diagram_types=["api", "unified_architecture"],
        include_sections=["architecture_diagrams", "api_architecture"],
    ))
    result = exporter.export(report, tmp_path)
    assert result.export_status == "completed", result.warnings
    output = tmp_path / result.managed_artifact_reference
    if result.output_format == "pdf":
        from pypdf import PdfReader
        content = "\n".join(page.extract_text() or "" for page in PdfReader(output).pages)
    elif result.output_format == "docx":
        from docx import Document
        content = "\n".join(item.text for item in Document(output).paragraphs)
    else:
        content = output.read_text(encoding="utf-8")
    assert "API Architecture" in content
    assert "Unified Architecture" in content
    assert "Repository Overview" not in content


def test_openapi_identifiers_match_validation():
    app = FastAPI()
    app.include_router(repository_reports.router)
    fields = app.openapi()["components"]["schemas"]["ReportConfiguration"]["properties"]
    assert fields["selected_diagram_types"]["items"]["enum"] == list(SUPPORTED_DIAGRAM_TYPES)
    assert fields["include_sections"]["items"]["enum"] == list(SECTION_ORDER)
    assert fields["exclude_sections"]["items"]["enum"] == list(SECTION_ORDER)
    assert set(SUPPORTED_DIAGRAM_TYPES) == {item.value for item in DiagramType} | {"unified_architecture"}
