import asyncio
import logging
import mimetypes
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from app.config.settings import settings
from app.repository.adapters.github_repository import GitHubRepositoryAdapter
from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.analysis.repository_analyzer import RepositoryAnalyzer
from app.repository.exceptions import (
    InvalidRepositorySourceError,
    RepositoryLimitExceededError,
    RepositoryNotFoundError,
    RepositorySecurityError,
    WorkspaceError,
)
from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters import (
    DOCXExporter,
    HTMLExporter,
    MarkdownExporter,
    PDFExporter,
)
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportExportResult,
    ReportFormat,
)
from app.repository.reporting.report_generator import ReportGenerator
from app.repository.review.architecture_review_service import ArchitectureReviewService
from app.repository.synthesis.architecture_synthesizer import ArchitectureSynthesizer
from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
from app.repository.workspace_manager import WorkspaceManager


logger = logging.getLogger(__name__)


class ReportNotFoundError(Exception):
    pass


class ArtifactNotFoundError(Exception):
    pass


class DuplicateExportError(Exception):
    pass


class ReportExportFailedError(Exception):
    pass


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: UUID
    format: ReportFormat
    file_name: str
    mime_type: str
    file_size: int


class RepositoryReportService:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager | None = None,
        local_adapter: LocalRepositoryAdapter | None = None,
        github_adapter: GitHubRepositoryAdapter | None = None,
        analyzer: RepositoryAnalyzer | None = None,
        visualizer: ArchitectureVisualizer | None = None,
        synthesizer: ArchitectureSynthesizer | None = None,
        reviewer: ArchitectureReviewService | None = None,
        report_generator: ReportGenerator | None = None,
        output_directory: str | Path | None = None,
    ):
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.local_adapter = local_adapter or LocalRepositoryAdapter(self.workspace_manager)
        self.github_adapter = github_adapter or GitHubRepositoryAdapter(self.workspace_manager)
        self.analyzer = analyzer or RepositoryAnalyzer(self.workspace_manager)
        self.visualizer = visualizer or ArchitectureVisualizer()
        self.synthesizer = synthesizer or ArchitectureSynthesizer()
        self.reviewer = reviewer or ArchitectureReviewService()
        self.report_generator = report_generator or ReportGenerator()
        self.output_directory = Path(
            output_directory or settings.report_artifact_directory
        ).expanduser().resolve()
        self._artifact_manager: ArtifactManager | None = None
        self._lock = threading.RLock()
        self._reports: dict[UUID, ArchitectureReport] = {}
        self._artifacts: dict[UUID, tuple[UUID, ReportFormat, str, str, int]] = {}
        self._exports_in_progress: set[tuple[UUID, ReportFormat]] = set()

    async def create_report(
        self,
        source_type: str,
        source_reference: str,
        branch: str | None,
        configuration: ReportConfiguration,
    ) -> tuple[RepositoryAnalysisResult, ArchitectureReport]:
        adapter = {
            "local": self.local_adapter,
            "github": self.github_adapter,
        }.get(source_type)
        if adapter is None:
            raise InvalidRepositorySourceError("Repository source type is unsupported.")

        snapshot = await adapter.retrieve(source_reference, branch=branch)
        try:
            analysis = await self.analyzer.aanalyze(snapshot)
            visualization = await asyncio.to_thread(self.visualizer.visualize, analysis)
            synthesis = await asyncio.to_thread(
                self.synthesizer.synthesize, analysis, visualization
            )
            review = await asyncio.to_thread(self.reviewer.review, synthesis, analysis)
            report = await asyncio.to_thread(
                self.report_generator.generate,
                analysis,
                visualization,
                configuration,
                synthesis=synthesis,
                review=review,
            )
            if source_type == "local":
                report._source_repository_root = str(
                    Path(source_reference).expanduser().resolve(strict=True)
                )
        finally:
            await asyncio.to_thread(
                self.workspace_manager.cleanup_workspace,
                snapshot.workspace_id,
            )

        with self._lock:
            self._reports[report.report_id] = report
        return analysis, report

    def get_report(self, report_id: UUID) -> ArchitectureReport:
        with self._lock:
            report = self._reports.get(report_id)
        if report is None:
            raise ReportNotFoundError
        return report

    async def export_report(
        self,
        report_id: UUID,
        output_format: ReportFormat,
    ) -> tuple[ReportExportResult, list[ArtifactRecord]]:
        report = self.get_report(report_id)
        export_key = (report_id, output_format)
        with self._lock:
            if export_key in self._exports_in_progress or any(
                item[0] == report_id and item[1] == output_format
                for item in self._artifacts.values()
            ):
                raise DuplicateExportError
            self._exports_in_progress.add(export_key)

        try:
            ArtifactManager.validate_output_directory(
                self.output_directory,
                report._source_repository_root,
            )
            manager = self._get_artifact_manager()
            before = self._report_files(manager, report_id)
            exporter = self._exporter(output_format, manager)
            result = await asyncio.to_thread(
                exporter.export, report, self.output_directory
            )
            if result.export_status != "completed":
                self._remove_new_report_files(manager, report_id, before)
                logger.warning(
                    "event=repository_report_export_failed report_id=%s format=%s",
                    report_id,
                    output_format.value,
                )
                raise ReportExportFailedError

            locations = self._report_files(manager, report_id)
            main_location = result.managed_artifact_reference or result.output_location
            if not main_location or main_location not in locations:
                self._remove_new_report_files(manager, report_id, before)
                raise ReportExportFailedError

            registered = []
            with self._lock:
                for location in sorted(locations, key=lambda item: (item != main_location, item)):
                    if location in before:
                        continue
                    path = self._safe_artifact_path(manager, location)
                    artifact_id = uuid4()
                    mime_type = result.mime_type if location == main_location else (
                        mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    )
                    file_size = result.file_size if location == main_location else path.stat().st_size
                    self._artifacts[artifact_id] = (
                        report_id,
                        output_format,
                        location,
                        mime_type,
                        file_size,
                    )
                    registered.append(ArtifactRecord(
                        artifact_id=artifact_id,
                        format=output_format,
                        file_name=path.name,
                        mime_type=mime_type,
                        file_size=file_size,
                    ))
            if not registered:
                raise ReportExportFailedError
            return result, registered
        finally:
            with self._lock:
                self._exports_in_progress.discard(export_key)

    def resolve_artifact(self, artifact_id: UUID) -> tuple[Path, str, str]:
        with self._lock:
            artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError
        _, _, location, mime_type, _ = artifact
        manager = self._get_artifact_manager()
        path = self._safe_artifact_path(manager, location)
        return path, path.name, mime_type

    def artifact_summaries(self, report_id: UUID) -> list[ArtifactRecord]:
        with self._lock:
            matches = [
                (artifact_id, metadata)
                for artifact_id, metadata in self._artifacts.items()
                if metadata[0] == report_id
            ]
        return [
            ArtifactRecord(
                artifact_id=artifact_id,
                format=format_value,
                file_name=PurePosixPath(location).name,
                mime_type=mime_type,
                file_size=size,
            )
            for artifact_id, (_, format_value, location, mime_type, size) in matches
        ]

    def _get_artifact_manager(self) -> ArtifactManager:
        with self._lock:
            if self._artifact_manager is None:
                self._artifact_manager = ArtifactManager(self.output_directory)
            return self._artifact_manager

    @staticmethod
    def _exporter(output_format: ReportFormat, manager: ArtifactManager):
        exporter_type = {
            ReportFormat.markdown: MarkdownExporter,
            ReportFormat.html: HTMLExporter,
            ReportFormat.pdf: PDFExporter,
            ReportFormat.docx: DOCXExporter,
        }[output_format]
        return exporter_type(manager)

    @staticmethod
    def _report_files(manager: ArtifactManager, report_id: UUID) -> set[str]:
        directory = manager.report_directory_for_cleanup(report_id)
        if directory is None:
            return set()
        return {
            path.relative_to(manager.output_root).as_posix()
            for path in directory.iterdir()
            if path.is_file() and not path.is_symlink()
        }

    @staticmethod
    def _remove_new_report_files(
        manager: ArtifactManager,
        report_id: UUID,
        existing: set[str],
    ) -> None:
        directory = manager.report_directory_for_cleanup(report_id)
        if directory is None:
            return
        for path in directory.iterdir():
            relative = path.relative_to(manager.output_root).as_posix()
            if relative not in existing and path.is_file() and not path.is_symlink():
                path.unlink()

    @staticmethod
    def _safe_artifact_path(manager: ArtifactManager, location: str) -> Path:
        relative = PurePosixPath(location)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ArtifactNotFoundError
        candidate = manager.output_root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve(strict=True)
            root = manager.output_root.resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError) as exc:
            raise ArtifactNotFoundError from exc
        if (
            candidate.is_symlink()
            or not resolved.is_file()
            or root not in resolved.parents
        ):
            raise ArtifactNotFoundError
        current = manager.output_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactNotFoundError
        return resolved


repository_report_service = RepositoryReportService()
