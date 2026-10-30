from pathlib import Path

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class MarkdownExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        warnings: list[str] = []
        manager = self.artifact_manager or ArtifactManager(output_directory)
        lines = [f"# {redact_sensitive_text(report.title)}", ""]
        for section in report.sections:
            lines.append(f"## {redact_sensitive_text(section.title)}")
            lines.append("")
            lines.append(redact_sensitive_text(section.content))
            if report.configuration.include_evidence and section.evidence_references:
                lines.append("")
                lines.append("Evidence: " + ", ".join(section.evidence_references))
            lines.append("")
        for diagram in report.diagrams:
            lines.append(f"### Diagram: {redact_sensitive_text(diagram.title)}")
            lines.append("")
            if report.configuration.include_rendered_diagrams and diagram.rendered_png:
                lines.append("> Rendered PNG diagram is available in the binary HTML/PDF/DOCX export variants.")
            if report.configuration.include_mermaid_source:
                lines.append("```mermaid")
                lines.append(redact_sensitive_text(diagram.mermaid_source))
                lines.append("```")
            if diagram.generation_warnings:
                lines.append("")
                lines.append("Warnings: " + "; ".join(
                    redact_sensitive_text(item) for item in diagram.generation_warnings
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
                warnings=[f"Markdown export failed: {type(exc).__name__}."],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.markdown,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            file_size=size,
            export_status="completed",
            warnings=warnings,
        )
