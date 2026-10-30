from typing import Protocol, runtime_checkable

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.visualization.models import ArchitectureVisualizationResult

from app.repository.synthesis.models import ArchitectureSynthesisResult


@runtime_checkable
class ArchitectureSynthesizerContract(Protocol):
    def synthesize(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult | None = None,
    ) -> ArchitectureSynthesisResult:
        ...
