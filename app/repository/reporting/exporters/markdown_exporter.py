from pathlib import Path
import re
from html import escape

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import (
    failed_export,
    get_artifact_manager,
    redact_sensitive_text,
    validate_export_report,
    valid_png,
)
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class MarkdownExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        try:
            validate_export_report(report)
        except ValueError as exc:
            return failed_export(report, ReportFormat.markdown, "md", f"Invalid report: {exc}")

        warnings: list[str] = []
        try:
            manager = get_artifact_manager(report, output_directory, self.artifact_manager)
        except (OSError, ValueError) as exc:
            return failed_export(
                report,
                ReportFormat.markdown,
                "md",
                f"Unsafe artifact output path: {type(exc).__name__}: {exc}",
            )
        lines = [
            f"# {_markdown_text(report.title)}",
            "",
            f"- Repository: {_markdown_text(report.repository_name)}",
            f"- Source type: {_markdown_text(report.repository_source_type)}",
            f"- Source reference: {_markdown_text(report.repository_reference)}",
            f"- Generated: {_markdown_text(report.report_metadata.generated_at)}",
            f"- Report version: {_markdown_text(report.report_metadata.report_version)}",
            "",
            "## Table of Contents",
            "",
        ]
        for section in report.sections:
            lines.append(f"- [{_markdown_text(section.title)}](#{_anchor(section.section_id)})")
        if report.diagrams:
            lines.append("- [Architecture Diagrams](#architecture-diagrams)")
        lines.append("")
        for section in report.sections:
            lines.append(f'<a id="{_anchor(section.section_id)}"></a>')
            lines.append(f"## {_markdown_text(section.title)}")
            lines.append("")
            lines.append(_markdown_text(section.content))
            if report.configuration.include_evidence and section.evidence_references:
                lines.append("")
                lines.append("Evidence: " + ", ".join(_markdown_text(item) for item in section.evidence_references))
            lines.append("")
        if report.diagrams:
            lines.extend(["<a id=\"architecture-diagrams\"></a>", "## Architecture Diagrams", ""])
        for diagram in report.diagrams:
            lines.append(f"### Diagram: {_markdown_text(diagram.title)}")
            lines.append("")
            if report.configuration.include_rendered_diagrams:
                if diagram.rendered_png and valid_png(diagram.rendered_png):
                    filename = "diagram-" + _anchor(diagram.diagram_id)[:80] + ".png"
                    _, relative, _ = manager.write_attachment(report.report_id, filename, diagram.rendered_png)
                    lines.append(f"![{_markdown_text(diagram.title)}]({Path(relative).name})")
                elif diagram.rendered_png:
                    warnings.append(f"Invalid rendered PNG for diagram {diagram.diagram_id}.")
                elif diagram.rendered_svg:
                    warnings.append(f"Rendered SVG for diagram {diagram.diagram_id} is not embedded in Markdown.")
                else:
                    warnings.append(f"No rendered image is available for diagram {diagram.diagram_id}.")
            if report.configuration.include_mermaid_source:
                lines.append("```mermaid")
                lines.append(_markdown_mermaid(diagram.mermaid_source))
                lines.append("```")
            if report.configuration.include_limitations and diagram.generation_warnings:
                lines.append("")
                lines.append("Warnings: " + "; ".join(
                    _markdown_text(item) for item in diagram.generation_warnings
                ))
            if report.configuration.include_evidence and diagram.evidence_references:
                lines.append("")
                lines.append("Evidence: " + ", ".join(diagram.evidence_references))
            lines.append("")
        try:
            _, relative, size = manager.write_text(report.report_id, "md", "\n".join(lines))
        except (OSError, ValueError) as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.markdown,
                output_file_name=manager.safe_filename(report.report_id, "md"),
                export_status="failed",
                warnings=[f"Markdown export failed: {type(exc).__name__}: {redact_sensitive_text(str(exc))}"],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.markdown,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            output_location=relative,
            file_size=size,
            mime_type="text/markdown",
            export_status="completed",
            warnings=[redact_sensitive_text(item) for item in warnings],
        )


def _anchor(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-") or "section"


def _markdown_text(value: str) -> str:
    safe = escape(redact_sensitive_text(str(value)), quote=False).replace("`", "'")
    safe = (
        safe.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
    return re.sub(r"(?m)^(\s{0,3})([#>])", r"\1\\\2", safe)


def _markdown_mermaid(value: str) -> str:
    return redact_sensitive_text(value).replace("```", "`\\`\\`")
