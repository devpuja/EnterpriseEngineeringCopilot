from datetime import datetime, timezone
import re

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportMetadata,
)
from app.repository.reporting.report_sections import ReportSections
from app.repository.visualization.models import ArchitectureVisualizationResult


class ReportGenerator:
    def __init__(self, report_sections: ReportSections | None = None):
        self.report_sections = report_sections or ReportSections()

    def generate(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
    ) -> ArchitectureReport:
        configuration = configuration or ReportConfiguration()
        now = datetime.now(timezone.utc).isoformat()
        sections = self.report_sections.build(analysis, visualization, configuration)
        selected = set(configuration.selected_diagram_types)
        diagrams = [
            diagram for diagram in visualization.diagrams
            if not selected or diagram.diagram_type.value in selected
        ]
        configured_diagrams = []
        for diagram in diagrams:
            diagram_copy = diagram.model_copy(deep=True)
            if not configuration.include_evidence:
                diagram_copy.evidence_references = []
                diagram_copy.evidence_map.nodes = {}
                diagram_copy.evidence_map.relationships = {}
                for node in diagram_copy.nodes:
                    node.evidence_references = []
                for relationship in diagram_copy.relationships:
                    relationship.evidence_references = []
            if not configuration.include_confidence:
                for relationship in diagram_copy.relationships:
                    if relationship.label and "confidence" in relationship.label.lower():
                        relationship.label = relationship.relationship_type.replace("_", " ")
                diagram_copy.mermaid_source = "\n".join(
                    re.sub(r"\|[^|]*confidence[^|]*\|", "|uses pattern|", line)
                    for line in diagram_copy.mermaid_source.splitlines()
                )
            if not configuration.include_limitations:
                diagram_copy.generation_warnings = []
            if not configuration.include_rendered_diagrams:
                diagram_copy.rendered_svg = None
                diagram_copy.rendered_png = None
            configured_diagrams.append(diagram_copy)
        return ArchitectureReport(
            analysis_id=analysis.analysis_id,
            repository_name=analysis.repository_name,
            title=configuration.title or "Architecture Analysis Report",
            sections=sections,
            diagrams=configured_diagrams,
            report_metadata=ReportMetadata(
                generated_at=now,
                report_version=configuration.report_version,
                organization_name=configuration.organization_name,
                project_name=configuration.project_name,
                options={},
            ),
            limitations=(
                list(dict.fromkeys([*analysis.limitations, *analysis.analysis_warnings, *visualization.visualization_warnings]))
                if configuration.include_limitations else []
            ),
            configuration=configuration.model_copy(deep=True),
        )
