from pathlib import Path
from io import BytesIO

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class PDFExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        manager = self.artifact_manager or ArtifactManager(output_directory)
        try:
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
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
                Paragraph(redact_sensitive_text(report.title), cover_style),
                Paragraph(redact_sensitive_text(report.repository_name), styles["Normal"]),
                Paragraph(report.report_metadata.generated_at, styles["Normal"]),
                PageBreak(),
            ]
            for section in report.sections:
                story.append(Paragraph(redact_sensitive_text(section.title), styles["Heading1"]))
                story.append(Paragraph(
                    redact_sensitive_text(section.content).replace("\n", "<br/>"),
                    styles["BodyText"],
                ))
                if section.evidence_references:
                    story.append(Paragraph(
                        "Evidence: " + ", ".join(section.evidence_references),
                        styles["BodyText"],
                    ))
                story.append(Spacer(1, 0.15 * inch))
            for diagram in report.diagrams:
                story.append(Paragraph(redact_sensitive_text(diagram.title), styles["Heading1"]))
                story.append(Paragraph("Mermaid source fallback:", styles["Heading2"]))
                story.append(Paragraph(
                    redact_sensitive_text(diagram.mermaid_source).replace("&", "&amp;").replace("\n", "<br/>"),
                    styles["Code"],
                ))
            document.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
            content = buffer.getvalue()
        except Exception as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.pdf,
                output_file_name=manager.safe_filename(report.report_id, "pdf"),
                export_status="failed",
                warnings=[f"PDF export failed: {type(exc).__name__}."],
            )

        try:
            _, relative, size = manager.write_bytes(report.report_id, "pdf", content)
        except (OSError, ValueError) as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.pdf,
                output_file_name=manager.safe_filename(report.report_id, "pdf"),
                export_status="failed",
                warnings=[f"PDF artifact write failed: {type(exc).__name__}."],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.pdf,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            file_size=size,
            export_status="completed",
        )
