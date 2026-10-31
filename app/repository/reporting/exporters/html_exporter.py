import html
from base64 import b64encode
from pathlib import Path

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import (
    failed_export,
    get_artifact_manager,
    redact_sensitive_text,
    svg_data_uri,
    validate_export_report,
    valid_png,
)
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class HTMLExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        try:
            validate_export_report(report)
        except ValueError as exc:
            return failed_export(report, ReportFormat.html, "html", f"Invalid report: {exc}")

        warnings: list[str] = []
        try:
            manager = get_artifact_manager(report, output_directory, self.artifact_manager)
        except (OSError, ValueError) as exc:
            return failed_export(
                report,
                ReportFormat.html,
                "html",
                f"Unsafe artifact output path: {type(exc).__name__}: {exc}",
            )
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
                    + "</p>" if report.configuration.include_evidence and section.evidence_references else ""
                )
                + "</section>"
            )
        diagram_blocks = []
        for diagram in report.diagrams:
            diagram_title = redact_sensitive_text(diagram.title)
            anchor = html.escape("diagram-" + diagram.diagram_id, quote=True)
            navigation.append(
                f'<a href="#{anchor}">{html.escape(diagram_title)}</a>'
            )
            block = (
                f'<section id="{anchor}"><h2>{html.escape(diagram_title)}</h2>'
                f'<p>{html.escape(redact_sensitive_text(diagram.description))}</p>'
            )
            if report.configuration.include_rendered_diagrams:
                if diagram.rendered_svg:
                    uri = svg_data_uri(diagram.rendered_svg)
                    if uri:
                        block += '<img class="architecture-diagram" alt="' + html.escape(diagram_title, quote=True) + '" src="' + uri + '">'
                    elif diagram.rendered_png:
                        if valid_png(diagram.rendered_png):
                            uri = "data:image/png;base64," + b64encode(diagram.rendered_png).decode("ascii")
                            block += '<img class="architecture-diagram" alt="' + html.escape(diagram_title, quote=True) + '" src="' + uri + '">'
                        else:
                            warnings.append(f"Invalid rendered PNG for diagram {diagram.diagram_id}.")
                    else:
                        warnings.append(f"Rendered SVG for diagram {diagram.diagram_id} was rejected.")
                elif diagram.rendered_png:
                    if valid_png(diagram.rendered_png):
                        uri = "data:image/png;base64," + b64encode(diagram.rendered_png).decode("ascii")
                        block += '<img class="architecture-diagram" alt="' + html.escape(diagram_title, quote=True) + '" src="' + uri + '">'
                    else:
                        warnings.append(f"Invalid rendered PNG for diagram {diagram.diagram_id}.")
                else:
                    warnings.append(f"No rendered image is available for diagram {diagram.diagram_id}.")
            if report.configuration.include_mermaid_source:
                block += (
                    '<pre><code class="language-mermaid">'
                    + html.escape(redact_sensitive_text(diagram.mermaid_source))
                    + "</code></pre>"
                )
            if report.configuration.include_evidence and diagram.evidence_references:
                block += "<p>Evidence: " + html.escape(", ".join(diagram.evidence_references)) + "</p>"
            if report.configuration.include_limitations and diagram.generation_warnings:
                block += "<p>Warnings: " + html.escape("; ".join(diagram.generation_warnings)) + "</p>"
            diagram_blocks.append(block + "</section>")
        metadata = (
            f'<dl><dt>Repository</dt><dd>{html.escape(redact_sensitive_text(report.repository_name))}</dd>'
            f'<dt>Source type</dt><dd>{html.escape(redact_sensitive_text(report.repository_source_type))}</dd>'
            f'<dt>Source reference</dt><dd>{html.escape(redact_sensitive_text(report.repository_reference))}</dd>'
            f'<dt>Generated</dt><dd>{html.escape(report.report_metadata.generated_at)}</dd>'
            f'<dt>Report version</dt><dd>{html.escape(report.report_metadata.report_version)}</dd></dl>'
        )
        document = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title>"
            "<style>body{font-family:Arial,sans-serif;max-width:960px;margin:auto;padding:24px;"
            "line-height:1.5;color:#202124}nav{display:flex;flex-wrap:wrap;gap:12px;margin:1.5rem 0}"
            "nav a{color:#145ea8}section{border-top:1px solid #ddd;padding:1rem 0}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:12px}"
            "img.architecture-diagram{max-width:100%;height:auto}dt{font-weight:bold}dd{margin:0 0 .5rem 0}"
            "@media print{nav{display:none}body{max-width:none;padding:0}section{break-inside:avoid}}</style></head><body>"
            f"<h1>{title}</h1>{metadata}<nav aria-label=\"Table of contents\">{''.join(navigation)}</nav>"
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
                warnings=[f"HTML export failed: {type(exc).__name__}: {redact_sensitive_text(str(exc))}"],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.html,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            output_location=relative,
            file_size=size,
            mime_type="text/html",
            export_status="completed",
            warnings=[redact_sensitive_text(item) for item in warnings],
        )
