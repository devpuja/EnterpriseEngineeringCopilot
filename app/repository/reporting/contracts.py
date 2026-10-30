from pathlib import Path
from typing import Protocol, runtime_checkable

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportExportResult,
)
from app.repository.visualization.models import ArchitectureVisualizationResult


@runtime_checkable
class ReportGeneratorContract(Protocol):
    def generate(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
    ) -> ArchitectureReport:
        ...


@runtime_checkable
class ReportExporterContract(Protocol):
    def export(
        self,
        report: ArchitectureReport,
        output_directory: Path,
    ) -> ReportExportResult:
        ...
