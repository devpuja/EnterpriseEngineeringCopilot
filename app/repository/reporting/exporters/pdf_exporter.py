from pathlib import Path
from io import BytesIO

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import (
    failed_export,
    get_artifact_manager,
    redact_sensitive_text,
    reportlab_text,
    validate_export_report,
    valid_png,
)
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class PDFExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        try:
            validate_export_report(report)
        except ValueError as exc:
            return failed_export(report, ReportFormat.pdf, "pdf", f"Invalid report: {exc}")

        warnings: list[str] = []
        try:
            manager = get_artifact_manager(report, output_directory, self.artifact_manager)
        except (OSError, ValueError) as exc:
            return failed_export(
                report,
                ReportFormat.pdf,
                "pdf",
                f"Unsafe artifact output path: {type(exc).__name__}: {exc}",
            )
        try:
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer
        except ImportError:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.pdf,
                output_file_name=manager.safe_filename(report.report_id, "pdf"),
                export_status="failed",
                warnings=["PDF export unavailable: reportlab dependency is not installed."],
            )

        buffer = BytesIO()
        styles = getSampleStyleSheet()
        cover_style = ParagraphStyle(
            "Cover",
            parent=styles["Title"],
            alignment=TA_CENTER,
            spaceAfter=0.4 * inch,
        )

        def header_footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.drawString(0.5 * inch, 0.35 * inch, redact_sensitive_text(report.repository_name))
            canvas.drawRightString(
                A4[0] - 0.5 * inch,
                0.35 * inch,
                f"Page {document.page}",
            )
            canvas.restoreState()

        try:
            document = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=0.5 * inch,
                leftMargin=0.5 * inch,
                topMargin=0.6 * inch,
                bottomMargin=0.6 * inch,
            )
            story = [
                Spacer(1, 2 * inch),
                Paragraph(reportlab_text(report.title), cover_style),
                Paragraph(reportlab_text(report.repository_name), styles["Normal"]),
                Paragraph(reportlab_text(f"Source type: {report.repository_source_type}"), styles["Normal"]),
                Paragraph(reportlab_text(f"Source reference: {report.repository_reference}"), styles["Normal"]),
                Paragraph(report.report_metadata.generated_at, styles["Normal"]),
                Paragraph(reportlab_text(f"Report version: {report.report_metadata.report_version}"), styles["Normal"]),
                PageBreak(),
                Paragraph("Table of Contents", styles["Heading1"]),
            ]
            for section in report.sections:
                story.append(Paragraph(reportlab_text(section.title), styles["BodyText"]))
            story.append(PageBreak())
            for section in report.sections:
                story.append(Paragraph(reportlab_text(section.title), styles["Heading1"]))
                story.append(Paragraph(
                    reportlab_text(section.content),
                    styles["BodyText"],
                ))
                if report.configuration.include_evidence and section.evidence_references:
                    story.append(Paragraph(
                        reportlab_text("Evidence: " + ", ".join(section.evidence_references)),
                        styles["BodyText"],
                    ))
                story.append(Spacer(1, 0.15 * inch))
            for diagram in report.diagrams:
                story.append(Paragraph(reportlab_text(diagram.title), styles["Heading1"]))
                if report.configuration.include_rendered_diagrams and diagram.rendered_png:
                    try:
                        if not valid_png(diagram.rendered_png):
                            raise ValueError("Invalid PNG content.")
                        image = Image(BytesIO(diagram.rendered_png), width=6.2 * inch, height=3.5 * inch, kind="proportional")
                        story.append(image)
                    except Exception as exc:
                        warnings.append(
                            f"Rendered image for diagram {diagram.diagram_id} could not be embedded: "
                            f"{type(exc).__name__}."
                        )
                elif report.configuration.include_rendered_diagrams and diagram.rendered_svg:
                    warnings.append(
                        f"SVG rendering for diagram {diagram.diagram_id} is not supported by the PDF exporter."
                    )
                elif report.configuration.include_rendered_diagrams:
                    warnings.append(f"No rendered image is available for diagram {diagram.diagram_id}.")
                if report.configuration.include_mermaid_source:
                    story.append(Paragraph(reportlab_text("Mermaid source fallback:"), styles["Heading2"]))
                    story.append(Paragraph(
                        reportlab_text(diagram.mermaid_source),
                        styles["Code"],
                    ))
                if report.configuration.include_evidence and diagram.evidence_references:
                    story.append(Paragraph(
                        reportlab_text("Evidence: " + ", ".join(diagram.evidence_references)),
                        styles["BodyText"],
                    ))
            document.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
            content = buffer.getvalue()
        except Exception as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.pdf,
                output_file_name=manager.safe_filename(report.report_id, "pdf"),
                export_status="failed",
                warnings=[f"PDF export failed: {type(exc).__name__}: {redact_sensitive_text(str(exc))}"],
            )

        try:
            _, relative, size = manager.write_bytes(report.report_id, "pdf", content)
        except (OSError, ValueError) as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.pdf,
                output_file_name=manager.safe_filename(report.report_id, "pdf"),
                export_status="failed",
                warnings=[f"PDF artifact write failed: {type(exc).__name__}: {redact_sensitive_text(str(exc))}"],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.pdf,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            output_location=relative,
            file_size=size,
            mime_type="application/pdf",
            export_status="completed",
            warnings=[redact_sensitive_text(item) for item in warnings],
        )
