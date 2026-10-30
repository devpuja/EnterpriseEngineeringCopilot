import html
from pathlib import Path

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class HTMLExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        manager = self.artifact_manager or ArtifactManager(output_directory)
        title = html.escape(redact_sensitive_text(report.title))
        navigation = []
        bodies = []
        for section in report.sections:
            anchor = html.escape(section.section_id, quote=True)
            navigation.append(f'<a href="#{anchor}">{html.escape(redact_sensitive_text(section.title))}</a>')
            bodies.append(
                f'<section id="{anchor}"><h2>{html.escape(redact_sensitive_text(section.title))}</h2>'
                f'<pre>{html.escape(redact_sensitive_text(section.content))}</pre>'
                + (
                    "<p>Evidence: "
                    + html.escape(", ".join(section.evidence_references))
                    + "</p>" if section.evidence_references else ""
                )
                + "</section>"
            )
        diagram_blocks = []
        for diagram in report.diagrams:
            diagram_blocks.append(
                "<section><h2>" + html.escape(redact_sensitive_text(diagram.title)) + "</h2>"
                "<pre><code>" + html.escape(redact_sensitive_text(diagram.mermaid_source)) + "</code></pre>"
                "</section>"
            )
        document = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title>"
            "<style>body{font-family:Arial,sans-serif;max-width:960px;margin:auto;padding:24px;"
            "line-height:1.45}nav{display:flex;flex-wrap:wrap;gap:12px}table{border-collapse:collapse}"
            "th,td{border:1px solid #aaa;padding:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "@media print{nav{display:none}}</style></head><body>"
            f"<h1>{title}</h1><nav>{''.join(navigation)}</nav>"
            + "".join(bodies)
            + "".join(diagram_blocks)
            + "</body></html>"
        )
        try:
            _, relative, size = manager.write_text(report.report_id, "html", document)
        except (OSError, ValueError) as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.html,
                output_file_name=manager.safe_filename(report.report_id, "html"),
                export_status="failed",
                warnings=[f"HTML export failed: {type(exc).__name__}."],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.html,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            file_size=size,
            export_status="completed",
        )
