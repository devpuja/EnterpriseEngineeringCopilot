import re

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ReportConfiguration, ReportSection
from app.repository.review.models import ArchitectureReviewResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.visualization.models import ArchitectureVisualizationResult


class ReportSections:
    def build(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
        synthesis: ArchitectureSynthesisResult | None = None,
        review: ArchitectureReviewResult | None = None,
    ) -> list[ReportSection]:
        configuration = configuration or ReportConfiguration()
        sections: list[ReportSection] = []
        diagrams = list(visualization.diagrams)
        if synthesis and synthesis.unified_diagram and all(
            item.diagram_id != synthesis.unified_diagram.diagram_id for item in diagrams
        ):
            diagrams.append(synthesis.unified_diagram.model_copy(deep=True))
        selected_visualization_diagrams = [
            diagram for diagram in diagrams
            if not configuration.selected_diagram_types
            or diagram.diagram_type.value in configuration.selected_diagram_types
            or (
                diagram.diagram_id == "unified_architecture"
                and "unified_architecture" in configuration.selected_diagram_types
            )
        ]

        def add(section_id: str, title: str, content: str, evidence: list[str] | None = None, diagrams: list[str] | None = None):
            mandatory_section = section_id in {"limitations", "evidence_references"}
            if configuration.include_sections and not mandatory_section and section_id not in configuration.include_sections:
                return
            if section_id in configuration.exclude_sections:
                return
            selected_diagram_ids = {
                diagram.diagram_id for diagram in selected_visualization_diagrams
                if not configuration.selected_diagram_types
                or diagram.diagram_type.value in configuration.selected_diagram_types
                or (
                    diagram.diagram_id == "unified_architecture"
                    and "unified_architecture" in configuration.selected_diagram_types
                )
            }
            section_diagrams = [
                diagram_id for diagram_id in (diagrams or [])
                if diagram_id in selected_diagram_ids
            ]
            sections.append(ReportSection(
                section_id=section_id,
                title=redact_sensitive_text(title),
                content=redact_sensitive_text(content).strip(),
                evidence_references=(evidence or []) if configuration.include_evidence else [],
                related_diagram_ids=section_diagrams,
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
        executive_content = (
            f"{analysis.summary}\n\n"
            f"Main technologies: {technologies}.\n\n"
            + (
                f"Architecture synthesis: {synthesis.architecture_summary}\n\n"
                if synthesis else ""
            )
            + (
                f"Architecture review outcome: {review.overall_review_outcome.value}. "
                f"{review.review_summary}\n\n"
                if review else ""
            )
            + (
                "Key architecture risks: "
                + "; ".join(
                    f"{item.severity.value}: {item.title}"
                    for item in review.findings[:3]
                )
                + ".\n\n"
                if review and review.findings else ""
            )
            + (
                "Priority recommendations: "
                + "; ".join(item.recommendation for item in review.priority_recommendations[:3])
                + ".\n\n"
                if review and review.priority_recommendations else ""
            )
            + (
                "Important limitation: findings are based on static repository analysis; runtime behavior and deployment topology were not observed."
                if configuration.include_limitations else ""
            )
        )
        add("executive_summary", "Executive Summary", executive_content)

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
            f"Project structure: {analysis.project_structure.summary}\n"
            f"Source directories: {', '.join(analysis.project_structure.source_directories) or 'Not identified'}\n"
            f"Test directories: {', '.join(analysis.project_structure.test_directories) or 'Not identified'}\n"
            f"Configuration locations: {', '.join(analysis.project_structure.config_locations) or 'Not identified'}\n"
            f"Infrastructure locations: {', '.join(analysis.project_structure.infrastructure_locations) or 'Not identified'}\n"
            f"Shared libraries: {', '.join(analysis.project_structure.shared_libraries) or 'Not identified'}"
        ), sorted({
            evidence
            for item in [*analysis.projects, *analysis.application_entry_points]
            for evidence in item.evidence_references
        }))

        patterns = "\n".join(
            f"- {item.name}: {item.explanation}"
            + (f" (confidence: {item.confidence.value})" if configuration.include_confidence else "")
            + (f"; limitation: {item.limitations}" if configuration.include_limitations else "")
            for item in analysis.architectural_patterns
            if item.name.lower() != "not determined"
        ) or "- No sufficiently supported architecture pattern was identified."
        add(
            "existing_architecture",
            "Existing Architecture",
            patterns,
            diagrams=[
                diagram.diagram_id for diagram in diagrams
                if diagram.diagram_type.value == "architecture_pattern"
            ],
        )

        add(
            "architecture_diagrams",
            "Architecture Diagrams",
            "\n".join(f"- {item.title} (`{item.diagram_id}`)" for item in selected_visualization_diagrams)
            or "- No architecture diagrams were generated.",
            diagrams=[item.diagram_id for item in selected_visualization_diagrams],
        )

        technology_lines = "\n".join(
            f"- {item.name} ({item.category}"
            + (f", {item.confidence.value}" if configuration.include_confidence else "")
            + ")"
            for item in analysis.technology_stack
        ) or "- No supported technology findings were identified."
        add("technology_stack", "Technology Stack", technology_lines, sorted({
            evidence for item in analysis.technology_stack for evidence in item.evidence_references
        }))

        dependency_lines = "\n".join(
            f"- {item.source} --{item.dependency_type}--> {item.target} "
            f"(resolved: {'yes' if item.resolved else 'no'}"
            + (f", confidence: {item.confidence.value}" if configuration.include_confidence else "")
            + ")"
            for item in analysis.dependencies
        ) or "- No supported project dependency findings were identified."
        add(
            "components_dependencies",
            "Component and Dependency Analysis",
            dependency_lines,
            sorted({ref for item in analysis.dependencies for ref in item.evidence_references}),
            diagrams=[
                item.diagram_id for item in diagrams
                if item.diagram_type.value in {"component", "dependency"}
            ],
        )

        exposed = [item for item in analysis.api_endpoints if item.exposure.lower() == "exposed"]
        consumed = [item for item in analysis.api_endpoints if item.exposure.lower() == "consumed"]
        api_lines = "\n".join([
            "Exposed APIs:",
            *[f"- {item.method} {item.route} ({item.framework})" for item in exposed],
            "Consumed APIs:",
            *[f"- {item.method} {item.route} ({item.framework})" for item in consumed],
        ] if exposed or consumed else ["- No supported API findings were identified."])
        add(
            "api_architecture",
            "API Architecture",
            "\n".join(api_lines),
            sorted({ref for item in analysis.api_endpoints for ref in item.evidence_references}),
            diagrams=[item.diagram_id for item in diagrams if item.diagram_type.value == "api"],
        )

        database_lines = "\n".join(
            f"- {item.technology}: {item.evidence_type} in `{item.relative_path}`: {item.detail}"
            + (f" ({item.confidence.value})" if configuration.include_confidence else "")
            for item in analysis.database_findings
        ) or "- No supported database or persistence findings were identified."
        add(
            "database_architecture",
            "Database and Persistence Architecture",
            database_lines,
            sorted({ref for item in analysis.database_findings for ref in item.evidence_references}),
            diagrams=[item.diagram_id for item in diagrams if item.diagram_type.value == "database"],
        )

        integration_lines = "\n".join(
            f"- {item.name}: {item.integration_type}, status {item.status}"
            + (f", source `{item.relative_path}`" if item.relative_path else "")
            + f": {item.detail}"
            + (f", confidence: {item.confidence.value}" if configuration.include_confidence else "")
            for item in analysis.external_integrations
        ) or "- No supported external integration findings were identified."
        add(
            "external_integrations",
            "External Integrations",
            integration_lines,
            sorted({ref for item in analysis.external_integrations for ref in item.evidence_references}),
            diagrams=[item.diagram_id for item in diagrams if item.diagram_type.value == "integration"],
        )

        add("architecture_findings", "Architecture Findings and Observations", (
            f"{analysis.summary}\n\nNo unsupported quality, vulnerability, or security conclusions are included."
        ))

        if synthesis:
            add("architecture_synthesis", "Architecture Synthesis", synthesis.architecture_summary)
            components = "\n".join(
                f"- {item.name} [{item.component_type}]: {item.description}"
                + (f" (confidence: {item.confidence.value})" if configuration.include_confidence else "")
                for item in synthesis.components
            ) or "- No architecture components were synthesized."
            add(
                "architecture_components",
                "Synthesized Components and Responsibilities",
                components,
                [ref for item in synthesis.components for ref in item.evidence_references],
            )
            relationships = "\n".join(
                f"- {item.source_component_id} --{item.relationship_type}--> {item.target_component_id}: "
                f"{item.description} [{item.status.value}]"
                + (f" (confidence: {item.confidence.value})" if configuration.include_confidence else "")
                for item in synthesis.relationships
            ) or "- No architecture relationships were synthesized."
            add(
                "architecture_relationships",
                "Architecture Relationships",
                relationships,
                [ref for item in synthesis.relationships for ref in item.evidence_references],
            )
            data_flows = "\n".join(
                f"- {item.source_component_id} -> {item.target_component_id}: {item.flow_description}"
                f" ({item.interaction_type or 'interaction'}, {item.status.value})"
                + (f", confidence: {item.confidence.value}" if configuration.include_confidence else "")
                for item in synthesis.data_flows
            ) or "- No evidence-supported data flows were synthesized."
            add(
                "architecture_data_flows",
                "Architecture Data Flows",
                data_flows,
                [ref for item in synthesis.data_flows for ref in item.evidence_references],
            )
            external_systems = "\n".join(
                f"- {item.name} [{item.integration_type}, {item.status.value}]: {item.description}"
                + (f" (confidence: {item.confidence.value})" if configuration.include_confidence else "")
                for item in synthesis.external_systems
            ) or "- No external systems were synthesized."
            add(
                "external_systems",
                "External Systems and Integration Boundaries",
                external_systems,
                [ref for item in synthesis.external_systems for ref in item.evidence_references],
            )
        else:
            add(
                "architecture_synthesis",
                "Architecture Synthesis",
                "No architecture synthesis result was supplied; components, relationships, and data flows are unavailable.",
            )

        if review:
            add(
                "architecture_review",
                "Architecture Review",
                f"Overall outcome: {review.overall_review_outcome.value}\n\n{review.review_summary}",
            )
            findings = "\n\n".join(
                f"- [{item.severity.value.upper()}] {item.title} ({item.category.value}; {item.status.value}): "
                f"{item.description}\n  Affected components: {', '.join(item.affected_component_ids) or 'Not specified'}\n"
                f"  Related relationships: {', '.join(item.related_relationship_references) or 'None'}\n"
                f"  Related data flows: {', '.join(item.related_data_flow_references) or 'None'}\n"
                f"  Recommendation: {item.recommendation}"
                + (f"\n  Confidence: {item.confidence.value}" if configuration.include_confidence else "")
                for item in review.findings
            ) or "- No architecture review findings were recorded."
            add(
                "review_findings",
                "Architecture Review Findings",
                findings,
                [ref for item in review.findings for ref in item.evidence_references],
            )
            strengths = "\n".join(
                f"- {item.title}: {item.description}"
                f" (components: {', '.join(item.affected_component_ids) or 'Not specified'})"
                + (f" (confidence: {item.confidence.value})" if configuration.include_confidence else "")
                for item in review.strengths
            ) or "- No positive architecture observations were recorded."
            add(
                "architecture_strengths",
                "Positive Architecture Observations",
                strengths,
                [ref for item in review.strengths for ref in item.evidence_references],
            )
            recommendations = "\n\n".join(
                f"- [{item.priority.upper()} priority] {item.recommendation}\n"
                f"  Benefits: {', '.join(item.benefits) or 'Not specified'}\n"
                f"  Trade-offs: {', '.join(item.trade_offs) or 'Not specified'}\n"
                f"  Implementation: {', '.join(item.implementation_considerations) or 'Not specified'}"
                for item in review.priority_recommendations
            ) or "\n\n".join(
                f"- {item.recommendation}\n  Benefits: {', '.join(item.benefits) or 'Not specified'}\n"
                f"  Trade-offs: {', '.join(item.trade_offs) or 'Not specified'}\n"
                f"  Implementation: {', '.join(item.implementation_considerations) or 'Not specified'}"
                for item in review.findings
            ) or "- No recommendations were recorded."
            add(
                "recommendations",
                "Priority Recommendations",
                recommendations,
                [ref for item in review.findings for ref in item.evidence_references],
            )
        else:
            add(
                "architecture_review",
                "Architecture Review",
                "No architecture review result was supplied; review outcome and recommendations are unavailable.",
            )

        limitations = list(dict.fromkeys([
            *analysis.limitations,
            *analysis.analysis_warnings,
            *visualization.visualization_warnings,
            *(
                warning
                for diagram in diagrams
                for warning in diagram.generation_warnings
            ),
            *(synthesis.limitations + synthesis.warnings if synthesis else []),
            *(
                synthesis.unified_diagram.generation_warnings
                if synthesis and synthesis.unified_diagram else []
            ),
            *(review.limitations + review.warnings if review else []),
        ]))
        limitation_content = "\n".join(f"- {item}" for item in limitations) or "- Static analysis limitations could not be determined."
        if configuration.include_limitations:
            add("limitations", "Limitations and Unknowns", limitation_content)

        evidence_lines = "\n".join(
            f"- {item.evidence_id}: `{item.relative_path}` ({item.category.value}) - {item.explanation}"
            for item in analysis.evidence
        ) or "- No evidence references were recorded."
        if configuration.include_evidence:
            add("evidence_references", "Evidence References", evidence_lines, sorted(
                item.evidence_id for item in analysis.evidence
            ))

        add("appendix", "Appendix", (
            f"- Analysis ID: {analysis.analysis_id}\n"
            f"- Repository: {analysis.repository_name}\n"
            f"- Visualization result: {visualization.result_id}\n"
            "- Supported scope: static repository analysis for .NET/C#, Python, Angular, and React technologies.\n"
            f"- Diagram count: {len(selected_visualization_diagrams)}"
        ), diagrams=[item.diagram_id for item in selected_visualization_diagrams])
        return sections

    @staticmethod
    def _safe_source_reference(analysis: RepositoryAnalysisResult) -> str:
        source = analysis.source_reference.strip()
        if analysis.source_type.lower() == "github":
            return source
        if re.match(r"^[A-Za-z]:[\\/]", source) or source.startswith("/") or "\\" in source:
            return "Managed local repository (absolute path withheld)"
        return source[:200]
