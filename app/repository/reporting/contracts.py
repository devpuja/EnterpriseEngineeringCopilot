from pathlib import Path
from typing import Protocol, runtime_checkable

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportExportResult,
)
from app.repository.review.models import ArchitectureReviewResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.visualization.models import ArchitectureVisualizationResult


@runtime_checkable
class ReportGeneratorContract(Protocol):
    def generate(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
        *,
        synthesis: ArchitectureSynthesisResult | None = None,
        review: ArchitectureReviewResult | None = None,
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
