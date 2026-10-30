from typing import Protocol, runtime_checkable

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.visualization.models import (
    ArchitectureVisualizationResult,
    DiagramGenerationMetadata,
)


@runtime_checkable
class DiagramGeneratorContract(Protocol):
    def generate(self, analysis: RepositoryAnalysisResult) -> list[object]:
        ...


@runtime_checkable
class ArchitectureVisualizerContract(Protocol):
    def visualize(
        self,
        analysis: RepositoryAnalysisResult,
        metadata: DiagramGenerationMetadata | None = None,
    ) -> ArchitectureVisualizationResult:
        ...


@runtime_checkable
class DiagramRendererContract(Protocol):
    def render_svg(self, mermaid_source: str) -> str | None:
        ...

    def render_png(self, mermaid_source: str) -> bytes | None:
        ...
