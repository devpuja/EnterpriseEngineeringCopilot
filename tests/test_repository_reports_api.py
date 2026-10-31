from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import repository_reports as repository_reports_api
from app.config.settings import settings
from app.repository.adapters.github_repository import GitHubRepositoryAdapter
from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.reporting.models import ReportFormat
from app.repository.workspace_manager import WorkspaceManager
from app.services.repository_report_service import RepositoryReportService
from main import app


client = TestClient(app)


@pytest.fixture
def repository_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed_root = tmp_path / "allowed"
    repository = allowed_root / "sample"
    repository.mkdir(parents=True)
    (repository / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "1.0"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "allowed_local_repository_roots", [str(allowed_root)])
    workspace_manager = WorkspaceManager(
        tmp_path / "workspaces",
        retention_seconds=3600,
    )
    service = RepositoryReportService(
        workspace_manager=workspace_manager,
        local_adapter=LocalRepositoryAdapter(
            workspace_manager,
            allowed_roots=[str(allowed_root)],
        ),
        github_adapter=GitHubRepositoryAdapter(workspace_manager),
        output_directory=tmp_path / "artifacts",
    )
    monkeypatch.setattr(repository_reports_api, "repository_report_service", service)
    return repository, workspace_manager, service


def create_report(repository: Path) -> dict:
    response = client.post(
        "/api/v1/repository-reports/analyses",
        json={
            "source_type": "local",
            "source_reference": str(repository),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_repository_api_analyzes_builds_report_and_exports_all_formats(repository_api):
    repository, workspace_manager, service = repository_api
    payload = create_report(repository)
    report_id = payload["report"]["report_id"]

    assert payload["analysis"]["repository_name"] == "sample"
    assert payload["analysis"]["analysis_id"] == payload["report"]["analysis_id"]
    assert payload["report"]["section_ids"]
    assert payload["report"]["diagrams"]
    assert str(repository) not in str(payload)
    assert list(workspace_manager.workspace_root.iterdir()) == []

    report_response = client.get(f"/api/v1/repository-reports/{report_id}")
    assert report_response.status_code == 200
    assert report_response.json()["report_id"] == report_id

    for output_format in ReportFormat:
        export_response = client.post(
            f"/api/v1/repository-reports/{report_id}/exports",
            json={"format": output_format.value},
        )
        assert export_response.status_code == 201, export_response.text
        artifacts = export_response.json()["artifacts"]
        primary_artifact = next(
            item for item in artifacts
            if item["file_name"].endswith({
                ReportFormat.markdown: ".md",
                ReportFormat.html: ".html",
                ReportFormat.pdf: ".pdf",
                ReportFormat.docx: ".docx",
            }[output_format])
        )

        download_response = client.get(primary_artifact["download_url"])
        assert download_response.status_code == 200
        assert download_response.headers["content-disposition"].startswith("attachment;")
        if output_format == ReportFormat.pdf:
            assert download_response.content.startswith(b"%PDF")
        elif output_format == ReportFormat.docx:
            assert download_response.content.startswith(b"PK")
        else:
            assert download_response.content

    assert len(service.artifact_summaries(UUID(report_id))) >= len(ReportFormat)


def test_repository_api_rejects_unapproved_paths_and_unknown_resources(repository_api, tmp_path):
    _, _, _ = repository_api
    outside = tmp_path / "outside"
    outside.mkdir()
    denied = client.post(
        "/api/v1/repository-reports/analyses",
        json={"source_type": "local", "source_reference": str(outside)},
    )
    assert denied.status_code == 403
    invalid_github = client.post(
        "/api/v1/repository-reports/analyses",
        json={
            "source_type": "github",
            "source_reference": "http://github.com/example/repository",
        },
    )
    assert invalid_github.status_code == 400

    missing_id = str(uuid4())
    assert client.get(f"/api/v1/repository-reports/{missing_id}").status_code == 404
    assert client.post(
        f"/api/v1/repository-reports/{missing_id}/exports",
        json={"format": "markdown"},
    ).status_code == 404
    assert client.get(
        f"/api/v1/repository-reports/artifacts/{uuid4()}/download"
    ).status_code == 404


def test_repository_api_rejects_duplicate_and_invalid_exports(repository_api):
    repository, _, _ = repository_api
    report_id = create_report(repository)["report"]["report_id"]
    first = client.post(
        f"/api/v1/repository-reports/{report_id}/exports",
        json={"format": "markdown"},
    )
    assert first.status_code == 201

    duplicate = client.post(
        f"/api/v1/repository-reports/{report_id}/exports",
        json={"format": "markdown"},
    )
    assert duplicate.status_code == 409
    invalid_format = client.post(
        f"/api/v1/repository-reports/{report_id}/exports",
        json={"format": "exe"},
    )
    assert invalid_format.status_code == 422
    unknown_field = client.post(
        f"/api/v1/repository-reports/analyses",
        json={
            "source_type": "local",
            "source_reference": str(repository),
            "unexpected": True,
        },
    )
    assert unknown_field.status_code == 422


def test_repository_api_rejects_invalid_report_configuration(repository_api):
    repository, workspace_manager, _ = repository_api
    response = client.post(
        "/api/v1/repository-reports/analyses",
        json={
            "source_type": "local",
            "source_reference": str(repository),
            "configuration": {"selected_diagram_types": ["unsupported"]},
        },
    )
    assert response.status_code == 422
    assert list(workspace_manager.workspace_root.iterdir()) == []


def test_repository_api_prevents_exporting_into_source_repository(repository_api):
    repository, _, service = repository_api
    report_id = create_report(repository)["report"]["report_id"]
    service.output_directory = repository / "generated"

    response = client.post(
        f"/api/v1/repository-reports/{report_id}/exports",
        json={"format": "markdown"},
    )
    assert response.status_code == 422
    assert not service.output_directory.exists()
