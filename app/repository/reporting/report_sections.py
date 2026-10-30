import re

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.models import ReportConfiguration, ReportSection
from app.repository.visualization.models import ArchitectureVisualizationResult


class ReportSections:
    def build(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
    ) -> list[ReportSection]:
        configuration = configuration or ReportConfiguration()
        sections: list[ReportSection] = []

        def add(section_id: str, title: str, content: str, evidence: list[str] | None = None, diagrams: list[str] | None = None):
            if configuration.include_sections and section_id not in configuration.include_sections:
                return
            if section_id in configuration.exclude_sections:
                return
            sections.append(ReportSection(
                section_id=section_id,
                title=title,
                content=content.strip(),
                evidence_references=evidence or [],
                related_diagram_ids=diagrams or [],
            ))

        safe_source = self._safe_source_reference(analysis)
        add("cover", "Cover Page", (
            f"# {configuration.title or 'Architecture Analysis Report'}\n\n"
            f"- Repository: {analysis.repository_name}\n"
            f"- Source type: {analysis.source_type}\n"
            f"- Source reference: {safe_source}\n"
            f"- Report version: {configuration.report_version}"
        ))

        technologies = ", ".join(sorted({item.name for item in analysis.technology_stack})) or "No supported technology findings"
        add("executive_summary", "Executive Summary", (
            f"{analysis.summary}\n\n"
            f"Main technologies: {technologies}.\n\n"
            "Important limitation: findings are based on static repository analysis; runtime behavior and deployment topology were not observed."
        ))

        entry_points = "\n".join(
            f"- {item.entry_point_type}: `{item.relative_path}`"
            for item in analysis.application_entry_points
        ) or "- No supported application entry points were identified."
        projects = "\n".join(
            f"- {item.name} ({item.kind})"
            for item in analysis.projects
        ) or "- No supported project findings were identified."
        add("repository_overview", "Repository Overview", (
            f"- Repository: {analysis.repository_name}\n"
            f"- Source type: {analysis.source_type}\n"
            f"- Source reference: {safe_source}\n\n"
            f"Technology stack: {technologies}\n\n"
            f"Projects:\n{projects}\n\n"
            f"Application entry points:\n{entry_points}\n\n"
            f"Project structure: {analysis.project_structure.summary}"
        ), sorted({e for item in analysis.projects for e in item.evidence_references}))

        patterns = "\n".join(
            f"- {item.name}: {item.explanation} (confidence: {item.confidence.value}; limitation: {item.limitations})"
            for item in analysis.architectural_patterns
            if item.name.lower() != "not determined"
        ) or "- No sufficiently supported architecture pattern was identified."
        add("existing_architecture", "Existing Architecture", patterns, diagrams=[
            diagram.diagram_id for diagram in visualization.diagrams
            if diagram.diagram_type.value == "architecture_pattern"
        ])

        add(
            "architecture_diagrams",
            "Architecture Diagrams",
            "\n".join(f"- {item.title} (`{item.diagram_id}`)" for item in visualization.diagrams)
            or "- No architecture diagrams were generated.",
            diagrams=[item.diagram_id for item in visualization.diagrams],
        )

        technology_lines = "\n".join(
            f"- {item.name} ({item.category}, {item.confidence.value})"
            for item in analysis.technology_stack
        ) or "- No supported technology findings were identified."
        add("technology_stack", "Technology Stack", technology_lines, sorted({
            evidence for item in analysis.technology_stack for evidence in item.evidence_references
        }))

        dependency_lines = "\n".join(
            f"- {item.source} --{item.dependency_type}--> {item.target} "
            f"(resolved: {'yes' if item.resolved else 'no'}, confidence: {item.confidence.value})"
            for item in analysis.dependencies
        ) or "- No supported project dependency findings were identified."
        add("components_dependencies", "Component and Dependency Analysis", dependency_lines, diagrams=[
            item.diagram_id for item in visualization.diagrams
            if item.diagram_type.value in {"component", "dependency"}
        ])

        exposed = [item for item in analysis.api_endpoints if item.exposure.lower() == "exposed"]
        consumed = [item for item in analysis.api_endpoints if item.exposure.lower() == "consumed"]
        api_lines = "\n".join([
            "Exposed APIs:",
            *[f"- {item.method} {item.route} ({item.framework})" for item in exposed],
            "Consumed APIs:",
            *[f"- {item.method} {item.route} ({item.framework})" for item in consumed],
        ] if exposed or consumed else ["- No supported API findings were identified."])
        add("api_architecture", "API Architecture", "\n".join(api_lines), diagrams=[
            item.diagram_id for item in visualization.diagrams if item.diagram_type.value == "api"
        ])

        database_lines = "\n".join(
            f"- {item.technology}: {item.evidence_type} ({item.confidence.value})"
            for item in analysis.database_findings
        ) or "- No supported database or persistence findings were identified."
        add("database_architecture", "Database and Persistence Architecture", database_lines, diagrams=[
            item.diagram_id for item in visualization.diagrams if item.diagram_type.value == "database"
        ])

        integration_lines = "\n".join(
            f"- {item.name}: {item.integration_type}, status {item.status}, confidence {item.confidence.value}"
            for item in analysis.external_integrations
        ) or "- No supported external integration findings were identified."
        add("external_integrations", "External Integrations", integration_lines, diagrams=[
            item.diagram_id for item in visualization.diagrams if item.diagram_type.value == "integration"
        ])

        add("architecture_findings", "Architecture Findings and Observations", (
            f"{analysis.summary}\n\nNo unsupported quality, vulnerability, or security conclusions are included."
        ))

        limitations = list(dict.fromkeys([
            *analysis.limitations,
            *analysis.analysis_warnings,
            *visualization.visualization_warnings,
        ]))
        limitation_content = "\n".join(f"- {item}" for item in limitations) or "- Static analysis limitations could not be determined."
        add("limitations", "Limitations and Unknowns", limitation_content)

        evidence_lines = "\n".join(
            f"- {item.evidence_id}: `{item.relative_path}` ({item.category.value}) - {item.explanation}"
            for item in analysis.evidence
        ) or "- No evidence references were recorded."
        add("evidence_references", "Evidence References", evidence_lines, sorted(
            item.evidence_id for item in analysis.evidence
        ))

        add("appendix", "Appendix", (
            f"- Analysis ID: {analysis.analysis_id}\n"
            f"- Repository: {analysis.repository_name}\n"
            f"- Visualization result: {visualization.result_id}\n"
            "- Supported scope: static repository analysis for .NET/C#, Python, Angular, and React technologies.\n"
            f"- Diagram count: {len(visualization.diagrams)}"
        ), diagrams=[item.diagram_id for item in visualization.diagrams])
        return sections

    @staticmethod
    def _safe_source_reference(analysis: RepositoryAnalysisResult) -> str:
        source = analysis.source_reference.strip()
        if analysis.source_type.lower() == "github":
            return source
        if re.match(r"^[A-Za-z]:[\\/]", source) or source.startswith("/") or "\\" in source:
            return "Managed local repository (absolute path withheld)"
        return source[:200]
