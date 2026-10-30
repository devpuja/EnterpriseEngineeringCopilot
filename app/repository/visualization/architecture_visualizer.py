from datetime import datetime, timezone

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.visualization.diagram_generator import DiagramGenerator
from app.repository.visualization.diagram_renderer import DiagramRenderer
from app.repository.visualization.diagram_validator import DiagramValidator
from app.repository.visualization.models import (
    ArchitectureVisualizationResult,
    DiagramGenerationMetadata,
)


class ArchitectureVisualizer:
    def __init__(
        self,
        diagram_generator: DiagramGenerator | None = None,
        diagram_validator: DiagramValidator | None = None,
        diagram_renderer: DiagramRenderer | None = None,
        maximum_nodes: int = 30,
    ):
        self.diagram_generator = diagram_generator or DiagramGenerator(maximum_nodes=maximum_nodes)
        self.diagram_validator = diagram_validator or DiagramValidator(maximum_nodes=maximum_nodes)
        self.diagram_renderer = diagram_renderer or DiagramRenderer()
        self.maximum_nodes = maximum_nodes

    def visualize(
        self,
        analysis: RepositoryAnalysisResult,
        metadata: DiagramGenerationMetadata | None = None,
    ) -> ArchitectureVisualizationResult:
        diagrams = self.diagram_generator.generate(analysis)
        warnings: list[str] = []
        renderer_available = self.diagram_renderer.is_available()

        for diagram in diagrams:
            validation = self.diagram_validator.validate(diagram, analysis)
            if not validation.valid:
                diagram.generation_warnings.extend(validation.errors)
                warnings.append(
                    f"Diagram {diagram.diagram_id} failed structural validation: "
                    + "; ".join(validation.errors)
                )
            if renderer_available:
                diagram.rendered_svg = self.diagram_renderer.render_svg(diagram.mermaid_source)
                diagram.rendered_png = self.diagram_renderer.render_png(diagram.mermaid_source)
            elif not diagram.generation_warnings:
                warnings.append(
                    f"Diagram {diagram.diagram_id} rendered as Mermaid source only; renderer unavailable."
                )

        if metadata is None:
            metadata = DiagramGenerationMetadata(
                generated_at=datetime.now(timezone.utc).isoformat(),
                renderer_name="mermaid-cli" if renderer_available else "mermaid-source",
                deterministic=True,
                complexity_limit=self.maximum_nodes,
            )

        return ArchitectureVisualizationResult(
            analysis_id=analysis.analysis_id,
            repository_name=analysis.repository_name,
            diagrams=diagrams,
            visualization_warnings=warnings,
            generation_metadata=metadata,
        )
