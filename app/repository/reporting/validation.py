from pathlib import PurePosixPath, PureWindowsPath
from datetime import datetime

from app.repository.reporting.models import ArchitectureReport, ReportConfiguration
from app.repository.visualization.models import DiagramType


SECTION_ORDER = (
    "cover",
    "executive_summary",
    "repository_overview",
    "existing_architecture",
    "architecture_diagrams",
    "technology_stack",
    "components_dependencies",
    "api_architecture",
    "database_architecture",
    "external_integrations",
    "architecture_findings",
    "architecture_synthesis",
    "architecture_components",
    "architecture_relationships",
    "architecture_data_flows",
    "external_systems",
    "architecture_review",
    "review_findings",
    "architecture_strengths",
    "recommendations",
    "limitations",
    "evidence_references",
    "appendix",
)


class ReportValidationError(ValueError):
    """Raised when a canonical architecture report is incomplete or inconsistent."""


def validate_configuration(configuration: ReportConfiguration) -> None:
    known_sections = set(SECTION_ORDER)
    unknown_sections = (
        set(configuration.include_sections) | set(configuration.exclude_sections)
    ) - known_sections
    if unknown_sections:
        raise ReportValidationError(
            "configuration.sections: unknown section IDs: "
            + ", ".join(sorted(unknown_sections))
        )
    overlap = set(configuration.include_sections) & set(configuration.exclude_sections)
    if overlap:
        raise ReportValidationError(
            "configuration.sections: section IDs cannot be both included and excluded: "
            + ", ".join(sorted(overlap))
        )
    valid_diagrams = {item.value for item in DiagramType} | {"unified_architecture"}
    unknown_diagrams = set(configuration.selected_diagram_types) - valid_diagrams
    if unknown_diagrams:
        raise ReportValidationError(
            "configuration.selected_diagram_types: unsupported diagram types: "
            + ", ".join(sorted(unknown_diagrams))
        )


def validate_report(report: ArchitectureReport, require_marked: bool = False) -> None:
    validate_configuration(report.configuration)
    if not report.repository_name.strip():
        raise ReportValidationError("repository_name: value is required.")
    if not report.repository_source_type.strip():
        raise ReportValidationError("repository_source_type: value is required.")
    if not report.repository_reference.strip():
        raise ReportValidationError("repository_reference: value is required.")
    if not report.title.strip():
        raise ReportValidationError("title: value is required.")
    if not report.report_metadata.generated_at.strip():
        raise ReportValidationError("report_metadata.generated_at: value is required.")
    try:
        datetime.fromisoformat(report.report_metadata.generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportValidationError("report_metadata.generated_at: expected an ISO-8601 timestamp.") from exc
    if not report.report_metadata.report_version.strip():
        raise ReportValidationError("report_metadata.report_version: value is required.")
    if require_marked and not report.validated:
        raise ReportValidationError("report: export requires a validated report model.")
    if report.report_metadata.options.get("analysis_id") != str(report.analysis_id):
        raise ReportValidationError("report_metadata.options.analysis_id: does not match analysis_id.")
    if report.report_metadata.options.get("synthesis_id") != (
        str(report.synthesis_id) if report.synthesis_id else None
    ):
        raise ReportValidationError("report_metadata.options.synthesis_id: does not match synthesis_id.")
    if report.report_metadata.options.get("review_id") != (
        str(report.review_id) if report.review_id else None
    ):
        raise ReportValidationError("report_metadata.options.review_id: does not match review_id.")
    if report.report_metadata.options.get("configuration") != report.configuration.model_dump(mode="json"):
        raise ReportValidationError("report_metadata.options.configuration: does not match report configuration.")

    section_ids = [section.section_id for section in report.sections]
    if len(section_ids) != len(set(section_ids)):
        raise ReportValidationError("sections: section IDs must be unique.")
    positions = [SECTION_ORDER.index(item) for item in section_ids if item in SECTION_ORDER]
    if positions != sorted(positions):
        raise ReportValidationError("sections: sections are not in canonical order.")
    if report.configuration.include_sections:
        required_sections = set(report.configuration.include_sections)
        allowed = set(report.configuration.include_sections) | {
            section_id
            for section_id, enabled in (
                ("limitations", report.configuration.include_limitations),
                ("evidence_references", report.configuration.include_evidence),
            )
            if enabled and section_id not in report.configuration.exclude_sections
        }
    else:
        allowed = set(SECTION_ORDER)
        required_sections = {
            "cover",
            "executive_summary",
            "repository_overview",
            "architecture_diagrams",
            "appendix",
        }
        required_sections.update(
            section_id
            for section_id, enabled in (
                ("limitations", report.configuration.include_limitations),
                ("evidence_references", report.configuration.include_evidence),
            )
            if enabled
        )
    allowed -= set(report.configuration.exclude_sections)
    required_sections -= set(report.configuration.exclude_sections)
    missing_sections = required_sections - set(section_ids)
    if missing_sections:
        raise ReportValidationError(
            "sections: missing required section IDs " + ", ".join(sorted(missing_sections))
        )
    unexpected_sections = set(section_ids) - allowed
    if unexpected_sections:
        raise ReportValidationError(
            "sections: content violates configuration for "
            + ", ".join(sorted(unexpected_sections))
        )

    if len({diagram.diagram_id for diagram in report.diagrams}) != len(report.diagrams):
        raise ReportValidationError("diagrams: diagram IDs must be unique.")
    diagram_ids = {diagram.diagram_id for diagram in report.diagrams}
    if report.configuration.selected_diagram_types:
        unexpected_diagrams = {
            diagram.diagram_type.value
            for diagram in report.diagrams
            if diagram.diagram_type.value not in report.configuration.selected_diagram_types
            and not (
                diagram.diagram_id == "unified_architecture"
                and "unified_architecture" in report.configuration.selected_diagram_types
            )
        }
        if unexpected_diagrams:
            raise ReportValidationError(
                "diagrams: content violates configuration for "
                + ", ".join(sorted(unexpected_diagrams))
            )
    for section in report.sections:
        unknown_diagrams = set(section.related_diagram_ids) - diagram_ids
        if unknown_diagrams:
            raise ReportValidationError(
                f"sections.{section.section_id}.related_diagram_ids: unknown IDs "
                + ", ".join(sorted(unknown_diagrams))
            )

    evidence_ids = {item.evidence_id for item in report.evidence}
    if not report.configuration.include_evidence and report.evidence:
        raise ReportValidationError("evidence: content is present while evidence is disabled.")
    if not report.configuration.include_limitations and report.limitations:
        raise ReportValidationError("limitations: content is present while limitations are disabled.")
    if len(evidence_ids) != len(report.evidence):
        raise ReportValidationError("evidence: evidence IDs must be unique.")
    for item in report.evidence:
        _validate_relative_path(f"evidence.{item.evidence_id}.relative_path", item.relative_path)

    if report.synthesis is None:
        if report.synthesis_id is not None:
            raise ReportValidationError("synthesis_id: source synthesis is missing.")
        if report.review is not None or report.review_id is not None:
            raise ReportValidationError("review: a review requires its source synthesis.")
    else:
        if report.synthesis_id != report.synthesis.synthesis_id:
            raise ReportValidationError("synthesis_id: does not match the synthesis result.")
        if report.synthesis.original_analysis_id != report.analysis_id:
            raise ReportValidationError("synthesis.original_analysis_id: does not match analysis_id.")
        if report.synthesis.repository_name != report.repository_name:
            raise ReportValidationError("synthesis.repository_name: does not match repository_name.")
        synthesis_evidence = {
            reference
            for item in report.synthesis.components
            for reference in item.evidence_references
        }
        synthesis_evidence.update(
            reference
            for item in report.synthesis.relationships
            for reference in item.evidence_references
        )
        synthesis_evidence.update(
            reference
            for item in report.synthesis.data_flows
            for reference in item.evidence_references
        )
        synthesis_evidence.update(
            reference
            for item in report.synthesis.external_systems
            for reference in item.evidence_references
        )
        component_ids = {item.component_id for item in report.synthesis.components}
        component_ids.update(item.external_system_id for item in report.synthesis.external_systems)
        for relationship in report.synthesis.relationships:
            missing = {
                relationship.source_component_id,
                relationship.target_component_id,
            } - component_ids
            if missing:
                raise ReportValidationError(
                    "synthesis.relationships: unknown component IDs " + ", ".join(sorted(missing))
                )
        for flow in report.synthesis.data_flows:
            missing = {flow.source_component_id, flow.target_component_id} - component_ids
            if missing:
                raise ReportValidationError(
                    "synthesis.data_flows: unknown component IDs " + ", ".join(sorted(missing))
                )
        _validate_evidence_ids("synthesis", synthesis_evidence, evidence_ids)
        if (
            report.synthesis.unified_diagram
            and (
                not report.configuration.selected_diagram_types
                or "unified_architecture" in report.configuration.selected_diagram_types
                or "component" in report.configuration.selected_diagram_types
            )
        ):
            if report.synthesis.unified_diagram.diagram_id not in diagram_ids:
                raise ReportValidationError(
                    "synthesis.unified_diagram: diagram is missing from report.diagrams."
                )

    if report.review is not None:
        if report.review_id != report.review.review_id:
            raise ReportValidationError("review_id: does not match the review result.")
        if report.review.original_synthesis_id != report.synthesis_id:
            raise ReportValidationError("review.original_synthesis_id: does not match synthesis_id.")
        if (
            report.review.original_analysis_id is not None
            and report.review.original_analysis_id != report.analysis_id
        ):
            raise ReportValidationError("review.original_analysis_id: does not match analysis_id.")
        if report.review.repository_name != report.repository_name:
            raise ReportValidationError("review.repository_name: does not match repository_name.")
        known_components = (
            {item.component_id for item in report.synthesis.components}
            | {item.external_system_id for item in report.synthesis.external_systems}
            if report.synthesis
            else set()
        )
        for finding in report.review.findings:
            unknown_components = set(finding.affected_component_ids) - known_components
            if unknown_components:
                raise ReportValidationError(
                    f"review.findings.{finding.finding_id}.affected_component_ids: unknown IDs "
                    + ", ".join(sorted(unknown_components))
                )
            _validate_evidence_ids(
                f"review.findings.{finding.finding_id}",
                set(finding.evidence_references),
                evidence_ids,
            )
            relationship_ids = {
                f"{item.source_component_id}->{item.target_component_id}"
                for item in report.synthesis.relationships
            } | {
                f"{item.source_component_id}->{item.target_component_id}:{item.relationship_type}"
                for item in report.synthesis.relationships
            }
            unknown_relationships = (
                set(finding.related_relationships)
                | set(finding.related_relationship_references)
            ) - relationship_ids
            if unknown_relationships:
                raise ReportValidationError(
                    f"review.findings.{finding.finding_id}.related_relationship_references: unknown references "
                    + ", ".join(sorted(unknown_relationships))
                )
            flow_ids = {
                f"{item.source_component_id}->{item.target_component_id}:"
                f"{item.interaction_type or 'interaction'}"
                for item in report.synthesis.data_flows
            }
            unknown_flows = (
                set(finding.related_data_flows)
                | set(finding.related_data_flow_references)
            ) - flow_ids
            if unknown_flows:
                raise ReportValidationError(
                    f"review.findings.{finding.finding_id}.related_data_flow_references: unknown references "
                    + ", ".join(sorted(unknown_flows))
                )
        for strength in report.review.strengths:
            unknown_components = set(strength.affected_component_ids) - known_components
            if unknown_components:
                raise ReportValidationError(
                    "review.strengths.affected_component_ids: unknown IDs "
                    + ", ".join(sorted(unknown_components))
                )
            _validate_evidence_ids(
                "review.strengths",
                set(strength.evidence_references),
                evidence_ids,
            )
        recommendation_section = next(
            (item for item in report.sections if item.section_id == "recommendations"),
            None,
        )
        if recommendation_section:
            missing_recommendations = [
                item.recommendation
                for item in report.review.priority_recommendations
                if item.recommendation not in recommendation_section.content
            ]
            if missing_recommendations:
                raise ReportValidationError(
                    "sections.recommendations: priority recommendations are missing from the canonical report."
                )

    for section in report.sections:
        _validate_evidence_ids(
            f"sections.{section.section_id}",
            set(section.evidence_references),
            evidence_ids,
        )
    for diagram in report.diagrams:
        if not report.configuration.include_mermaid_source and diagram.mermaid_source:
            raise ReportValidationError(
                f"diagrams.{diagram.diagram_id}.mermaid_source: content is disabled by configuration."
            )
        if (
            not report.configuration.include_rendered_diagrams
            and (diagram.rendered_svg is not None or diagram.rendered_png is not None)
        ):
            raise ReportValidationError(
                f"diagrams.{diagram.diagram_id}: rendered content is disabled by configuration."
            )
        if not diagram.mermaid_source and report.configuration.include_mermaid_source:
            raise ReportValidationError(
                f"diagrams.{diagram.diagram_id}.mermaid_source: content is required by configuration."
            )
        _validate_evidence_ids(
            f"diagrams.{diagram.diagram_id}",
            set(diagram.evidence_references),
            evidence_ids,
        )
        diagram_evidence_ids = {
            item.evidence_id
            for node in diagram.nodes
            for item in node.evidence_references
        }
        diagram_evidence_ids.update(
            item.evidence_id
            for relationship in diagram.relationships
            for item in relationship.evidence_references
        )
        _validate_evidence_ids(
            f"diagrams.{diagram.diagram_id}.nodes_and_relationships",
            diagram_evidence_ids,
            evidence_ids,
        )


def _validate_evidence_ids(field: str, references: set[str], available: set[str]) -> None:
    missing = references - available
    if missing:
        raise ReportValidationError(
            f"{field}.evidence_references: unknown evidence IDs " + ", ".join(sorted(missing))
        )


def _validate_relative_path(field: str, value: str) -> None:
    path = PurePosixPath(value.replace("\\", "/"))
    windows_path = PureWindowsPath(value)
    if path.is_absolute() or windows_path.is_absolute() or ".." in path.parts:
        raise ReportValidationError(f"{field}: must be a safe repository-relative path.")
