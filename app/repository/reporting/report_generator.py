from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.reporting.exporters.base import (
    redact_sensitive_text,
    sanitize_png,
    sanitize_svg,
)
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportMetadata,
)
from app.repository.reporting.report_sections import ReportSections
from app.repository.reporting.validation import validate_configuration, validate_report
from app.repository.review.models import ArchitectureReviewResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.visualization.models import ArchitectureDiagram, ArchitectureVisualizationResult


class ReportGenerator:
    def __init__(self, report_sections: ReportSections | None = None):
        self.report_sections = report_sections or ReportSections()

    def generate(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult,
        configuration: ReportConfiguration | None = None,
        *,
        synthesis: ArchitectureSynthesisResult | None = None,
        review: ArchitectureReviewResult | None = None,
    ) -> ArchitectureReport:
        if analysis is None:
            raise ValueError("analysis result is required.")
        if visualization is None:
            raise ValueError("visualization result is required.")
        configuration = configuration or ReportConfiguration()
        validate_configuration(configuration)
        configuration = configuration.model_copy(update={
            "title": redact_sensitive_text(configuration.title) if configuration.title else None,
            "organization_name": (
                redact_sensitive_text(configuration.organization_name)
                if configuration.organization_name else None
            ),
            "project_name": (
                redact_sensitive_text(configuration.project_name)
                if configuration.project_name else None
            ),
            "report_version": redact_sensitive_text(configuration.report_version),
        })
        if visualization.analysis_id != analysis.analysis_id:
            raise ValueError("visualization.analysis_id does not match analysis.analysis_id.")
        if synthesis and synthesis.original_analysis_id != analysis.analysis_id:
            raise ValueError("synthesis.original_analysis_id does not match analysis.analysis_id.")
        if review and (
            synthesis is None
            or review.original_synthesis_id != synthesis.synthesis_id
        ):
            raise ValueError("review.original_synthesis_id does not match the supplied synthesis.")
        if review and review.original_analysis_id not in (None, analysis.analysis_id):
            raise ValueError("review.original_analysis_id does not match analysis.analysis_id.")

        now = datetime.now(timezone.utc).isoformat()
        sections = self.report_sections.build(
            analysis, visualization, configuration, synthesis, review
        )
        selected = set(configuration.selected_diagram_types)
        source_diagrams = list(visualization.diagrams)
        if synthesis and synthesis.unified_diagram and all(
            item.diagram_id != synthesis.unified_diagram.diagram_id for item in source_diagrams
        ):
            source_diagrams.append(synthesis.unified_diagram.model_copy(deep=True))
        diagrams = [diagram for diagram in source_diagrams if not selected or (
            diagram.diagram_type.value in selected
            or (diagram.diagram_id == "unified_architecture" and "unified_architecture" in selected)
        )]
        configured_diagrams = [
            _prepare_diagram(diagram, configuration) for diagram in diagrams
        ]

        synthesis_copy = _sanitized_model(synthesis) if synthesis else None
        review_copy = _sanitized_model(review) if review else None
        if synthesis_copy:
            if not configuration.include_evidence:
                for component in synthesis_copy.components:
                    component.evidence_references = []
                for relationship in synthesis_copy.relationships:
                    relationship.evidence_references = []
                for flow in synthesis_copy.data_flows:
                    flow.evidence_references = []
                for system in synthesis_copy.external_systems:
                    system.evidence_references = []
                if synthesis_copy.unified_diagram:
                    synthesis_copy.unified_diagram.evidence_references = []
                    synthesis_copy.unified_diagram.evidence_map.nodes = {}
                    synthesis_copy.unified_diagram.evidence_map.relationships = {}
                    for node in synthesis_copy.unified_diagram.nodes:
                        node.evidence_references = []
                    for relationship in synthesis_copy.unified_diagram.relationships:
                        relationship.evidence_references = []
            if not configuration.include_limitations:
                synthesis_copy.limitations = []
                synthesis_copy.warnings = []
            if synthesis.unified_diagram:
                synthesis_copy.unified_diagram = _prepare_diagram(
                    synthesis.unified_diagram, configuration
                )
        if review_copy:
            if not configuration.include_evidence:
                for finding in review_copy.findings:
                    finding.evidence_references = []
                for strength in review_copy.strengths:
                    strength.evidence_references = []
            if not configuration.include_limitations:
                review_copy.limitations = []
                review_copy.warnings = []

        repository_reference = self.report_sections._safe_source_reference(analysis)
        diagram_warnings = [
            warning
            for diagram in configured_diagrams
            for warning in diagram.generation_warnings
        ]
        if configuration.include_limitations and diagram_warnings:
            limitation_section = next(
                (section for section in sections if section.section_id == "limitations"),
                None,
            )
            if limitation_section:
                limitation_section.content = "\n".join([
                    limitation_section.content,
                    *(f"- {warning}" for warning in diagram_warnings),
                ]).strip()
        report = ArchitectureReport(
            analysis_id=analysis.analysis_id,
            repository_name=redact_sensitive_text(analysis.repository_name),
            repository_source_type=redact_sensitive_text(analysis.source_type),
            repository_reference=redact_sensitive_text(repository_reference),
            synthesis_id=synthesis.synthesis_id if synthesis else None,
            review_id=review.review_id if review else None,
            title=configuration.title or "Architecture Analysis Report",
            sections=sections,
            diagrams=configured_diagrams,
            evidence=(
                [_sanitized_model(item) for item in analysis.evidence]
                if configuration.include_evidence else []
            ),
            synthesis=synthesis_copy,
            review=review_copy,
            report_metadata=ReportMetadata(
                generated_at=now,
                report_version=configuration.report_version,
                organization_name=configuration.organization_name,
                project_name=configuration.project_name,
                options={
                    "analysis_id": str(analysis.analysis_id),
                    "synthesis_id": str(synthesis.synthesis_id) if synthesis else None,
                    "review_id": str(review.review_id) if review else None,
                    "configuration": {
                        **configuration.model_dump(mode="json"),
                    },
                },
            ),
            limitations=(
                list(dict.fromkeys([
                    *analysis.limitations,
                    *analysis.analysis_warnings,
                    *visualization.visualization_warnings,
                    *diagram_warnings,
                ]))
                + (synthesis_copy.limitations + synthesis_copy.warnings if synthesis_copy else [])
                + (review_copy.limitations + review_copy.warnings if review_copy else [])
                if configuration.include_limitations else []
            ),
            warnings=[
                *analysis.analysis_warnings,
                *visualization.visualization_warnings,
                *diagram_warnings,
                *(synthesis.warnings if synthesis else ["Architecture synthesis was not supplied."]),
                *(review.warnings if review else ["Architecture review was not supplied."]),
            ],
            configuration=configuration.model_copy(deep=True),
        )
        if analysis.source_type.lower() == "local":
            source_root = Path(analysis.source_reference).expanduser()
            if source_root.is_absolute():
                report._source_repository_root = str(source_root.resolve())
        report.warnings = list(dict.fromkeys(
            redact_sensitive_text(item) for item in report.warnings
        ))
        report.limitations = list(dict.fromkeys(
            redact_sensitive_text(item) for item in report.limitations
        ))
        validate_report(report)
        report.validated = True
        validate_report(report, require_marked=True)
        return report


def _sanitized_model(model: Any) -> Any:
    if model is None:
        return None
    data = model.model_dump(mode="python")

    def sanitize(value: Any) -> Any:
        if isinstance(value, str):
            return redact_sensitive_text(value)
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        return value

    return type(model).model_validate(sanitize(data))


def _prepare_diagram(
    diagram: ArchitectureDiagram,
    configuration: ReportConfiguration,
) -> ArchitectureDiagram:
    has_sensitive_text = _contains_redactable_text(diagram)
    has_confidence_text = _contains_confidence_text(diagram)
    has_excluded_evidence = (
        not configuration.include_evidence
        and any(
            evidence_id and (
                evidence_id in diagram.mermaid_source
                or evidence_id in (diagram.rendered_svg or "")
            )
            for evidence_id in diagram.evidence_references
        )
    )
    has_excluded_confidence = not configuration.include_confidence and has_confidence_text
    result = _sanitized_model(diagram)
    if not configuration.include_evidence:
        result.evidence_references = []
        result.evidence_map.nodes = {}
        result.evidence_map.relationships = {}
        for node in result.nodes:
            node.evidence_references = []
        for relationship in result.relationships:
            relationship.evidence_references = []
    if not configuration.include_confidence:
        for relationship in result.relationships:
            if relationship.label and "confidence" in relationship.label.lower():
                relationship.label = relationship.relationship_type.replace("_", " ")
        result.mermaid_source = re.sub(
            r"(?i)\|[^|]*confidence[^|]*\|", "|relationship|", result.mermaid_source
        )
    if not configuration.include_limitations:
        result.generation_warnings = []
    if not configuration.include_rendered_diagrams:
        result.rendered_svg = None
        result.rendered_png = None
    elif has_excluded_evidence or has_excluded_confidence:
        result.rendered_svg = None
        result.rendered_png = None
        _add_diagram_warning(
            result,
            configuration,
            "Rendered diagram was withheld because it may contain content excluded by report configuration.",
        )
    else:
        if result.rendered_svg:
            result.rendered_svg = sanitize_svg(result.rendered_svg)
            if result.rendered_svg is None:
                _add_diagram_warning(
                    result,
                    configuration,
                    "Rendered SVG was invalid or unsafe and was withheld.",
                )
        if result.rendered_png:
            if has_sensitive_text:
                result.rendered_png = None
                _add_diagram_warning(
                    result,
                    configuration,
                    "Rendered PNG was withheld because it may contain content excluded by report configuration."
                )
            else:
                result.rendered_png = sanitize_png(result.rendered_png)
                if result.rendered_png is None:
                    _add_diagram_warning(
                        result,
                        configuration,
                        "Rendered PNG was invalid and was withheld.",
                    )
    if not configuration.include_mermaid_source:
        result.mermaid_source = ""
    return result


def _add_diagram_warning(
    diagram: Any,
    configuration: ReportConfiguration,
    warning: str,
) -> None:
    if configuration.include_limitations:
        diagram.generation_warnings.append(warning)


def _contains_redactable_text(value: Any) -> bool:
    if isinstance(value, str):
        return redact_sensitive_text(value) != value
    if isinstance(value, list):
        return any(_contains_redactable_text(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_redactable_text(item) for item in value.values())
    if hasattr(value, "model_dump"):
        return _contains_redactable_text(value.model_dump(mode="python"))
    return False


def _contains_confidence_text(value: Any) -> bool:
    if isinstance(value, str):
        return "confidence" in value.lower()
    if isinstance(value, list):
        return any(_contains_confidence_text(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_confidence_text(item) for item in value.values())
    if hasattr(value, "model_dump"):
        return _contains_confidence_text(value.model_dump(mode="python"))
    return False
