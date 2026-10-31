import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.exceptions import (
    InvalidRepositorySourceError,
    RepositoryLimitExceededError,
    RepositoryNotFoundError,
    RepositorySecurityError,
    WorkspaceError,
)
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportFormat,
)
from app.services.repository_report_service import (
    ArtifactRecord,
    ArtifactNotFoundError,
    DuplicateExportError,
    ReportExportFailedError,
    ReportNotFoundError,
    RepositoryReportService,
    repository_report_service,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/repository-reports",
    tags=["Repository Reports"],
)


class RepositoryAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["local", "github"]
    source_reference: str = Field(min_length=1, max_length=2048)
    branch: str | None = Field(default=None, min_length=1, max_length=255)
    configuration: ReportConfiguration = Field(default_factory=ReportConfiguration)


class ReportExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ReportFormat


class ArtifactResponse(BaseModel):
    artifact_id: UUID
    format: ReportFormat
    file_name: str
    mime_type: str
    file_size: int
    download_url: str


class ReportSummaryResponse(BaseModel):
    report_id: UUID
    analysis_id: UUID
    repository_name: str
    title: str
    generated_at: str
    section_ids: list[str]
    diagrams: list[dict[str, str]]
    warnings: list[str]
    artifacts: list[ArtifactResponse]


class RepositoryAnalysisResponse(BaseModel):
    analysis: RepositoryAnalysisResult
    report: ReportSummaryResponse


class ReportExportResponse(BaseModel):
    report_id: UUID
    format: ReportFormat
    artifacts: list[ArtifactResponse]
    warnings: list[str]


def _artifact_responses(
    artifacts: list[ArtifactRecord],
) -> list[ArtifactResponse]:
    return [
        ArtifactResponse(
            artifact_id=item.artifact_id,
            format=item.format,
            file_name=item.file_name,
            mime_type=item.mime_type,
            file_size=item.file_size,
            download_url=(
                f"/api/v1/repository-reports/artifacts/{item.artifact_id}/download"
            ),
        )
        for item in artifacts
    ]


def _report_response(
    report: ArchitectureReport,
    service: RepositoryReportService,
) -> ReportSummaryResponse:
    return ReportSummaryResponse(
        report_id=report.report_id,
        analysis_id=report.analysis_id,
        repository_name=report.repository_name,
        title=report.title,
        generated_at=report.report_metadata.generated_at,
        section_ids=[section.section_id for section in report.sections],
        diagrams=[
            {"diagram_id": diagram.diagram_id, "title": diagram.title}
            for diagram in report.diagrams
        ],
        warnings=report.warnings,
        artifacts=_artifact_responses(service.artifact_summaries(report.report_id)),
    )


def _raise_repository_error(exc: Exception) -> None:
    if isinstance(exc, InvalidRepositorySourceError):
        raise HTTPException(status_code=400, detail="Repository source is invalid.") from exc
    if isinstance(exc, RepositorySecurityError):
        raise HTTPException(status_code=403, detail="Repository source is not permitted.") from exc
    if isinstance(exc, RepositoryNotFoundError):
        raise HTTPException(status_code=404, detail="Repository source could not be retrieved.") from exc
    if isinstance(exc, RepositoryLimitExceededError):
        raise HTTPException(status_code=413, detail="Repository exceeds configured analysis limits.") from exc
    if isinstance(exc, WorkspaceError):
        raise HTTPException(status_code=503, detail="Repository workspace is unavailable.") from exc


@router.post(
    "/analyses",
    response_model=RepositoryAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_repository(
    request: RepositoryAnalysisRequest,
    response: Response,
) -> RepositoryAnalysisResponse:
    service = repository_report_service
    try:
        analysis, report = await service.create_report(
            request.source_type,
            request.source_reference,
            request.branch,
            request.configuration,
        )
        response.headers["Location"] = f"/api/v1/repository-reports/{report.report_id}"
        return RepositoryAnalysisResponse(
            analysis=analysis,
            report=_report_response(report, service),
        )
    except (
        InvalidRepositorySourceError,
        RepositorySecurityError,
        RepositoryNotFoundError,
        RepositoryLimitExceededError,
        WorkspaceError,
    ) as exc:
        _raise_repository_error(exc)
    except ValueError as exc:
        logger.warning(
            "event=repository_report_generation_rejected error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=422,
            detail="Repository report could not be generated from the supplied configuration.",
        ) from exc
    except Exception as exc:
        logger.exception(
            "event=repository_report_generation_failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Repository analysis failed. Check application logs.",
        ) from exc


@router.get("/{report_id}", response_model=ReportSummaryResponse)
def get_repository_report(report_id: UUID) -> ReportSummaryResponse:
    service = repository_report_service
    try:
        return _report_response(service.get_report(report_id), service)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository report not found.") from exc


@router.post(
    "/{report_id}/exports",
    response_model=ReportExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def export_repository_report(
    report_id: UUID,
    request: ReportExportRequest,
) -> ReportExportResponse:
    service = repository_report_service
    try:
        result, artifacts = await service.export_report(report_id, request.format)
        return ReportExportResponse(
            report_id=report_id,
            format=request.format,
            artifacts=_artifact_responses(artifacts),
            warnings=result.warnings,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository report not found.") from exc
    except DuplicateExportError as exc:
        raise HTTPException(
            status_code=409,
            detail="This report format has already been exported.",
        ) from exc
    except ReportExportFailedError as exc:
        raise HTTPException(
            status_code=502,
            detail="Repository report export failed. Check application logs.",
        ) from exc
    except (OSError, ValueError) as exc:
        logger.warning(
            "event=repository_report_export_rejected report_id=%s format=%s error_type=%s",
            report_id,
            request.format.value,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=422,
            detail="Repository report export configuration is invalid.",
        ) from exc
    except Exception as exc:
        logger.exception(
            "event=repository_report_export_failed report_id=%s format=%s error_type=%s",
            report_id,
            request.format.value,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Repository report export failed. Check application logs.",
        ) from exc


@router.get("/artifacts/{artifact_id}/download")
def download_repository_artifact(artifact_id: UUID) -> FileResponse:
    try:
        path, filename, mime_type = repository_report_service.resolve_artifact(artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository report artifact not found.") from exc
    return FileResponse(path, media_type=mime_type, filename=filename)
