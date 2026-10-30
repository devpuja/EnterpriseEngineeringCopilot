from datetime import datetime, timezone

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
        return ArchitectureReport(
            analysis_id=analysis.analysis_id,
            repository_name=analysis.repository_name,
            title=configuration.title or "Architecture Analysis Report",
            sections=sections,
            diagrams=diagrams,
            report_metadata=ReportMetadata(
                generated_at=now,
                report_version=configuration.report_version,
                organization_name=configuration.organization_name,
                project_name=configuration.project_name,
                options={
                    "include_evidence": configuration.include_evidence,
                    "include_confidence": configuration.include_confidence,
                    "include_limitations": configuration.include_limitations,
                    "include_mermaid_source": configuration.include_mermaid_source,
                    "include_rendered_diagrams": configuration.include_rendered_diagrams,
                },
            ),
            limitations=list(dict.fromkeys(analysis.limitations)),
        )
