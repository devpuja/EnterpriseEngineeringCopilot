from pathlib import Path
from io import BytesIO

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


class DOCXExporter:
    def __init__(self, artifact_manager: ArtifactManager | None = None):
        self.artifact_manager = artifact_manager

    def export(self, report: ArchitectureReport, output_directory: Path) -> ReportExportResult:
        manager = self.artifact_manager or ArtifactManager(output_directory)
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.docx,
                output_file_name=manager.safe_filename(report.report_id, "docx"),
                export_status="failed",
                warnings=["DOCX export unavailable: python-docx dependency is not installed."],
            )

        try:
            document = Document()
            section = document.sections[0]
            section.header.paragraphs[0].text = redact_sensitive_text(report.repository_name)
            section.footer.paragraphs[0].text = redact_sensitive_text(report.title)

            title = document.add_paragraph()
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title.add_run(redact_sensitive_text(report.title)).bold = True
            document.add_paragraph(redact_sensitive_text(report.repository_name))
            document.add_paragraph(report.report_metadata.generated_at)
            document.add_page_break()

            for report_section in report.sections:
                document.add_heading(redact_sensitive_text(report_section.title), level=1)
                for line in redact_sensitive_text(report_section.content).splitlines():
                    document.add_paragraph(line)
                if report.configuration.include_evidence and report_section.evidence_references:
                    document.add_paragraph(
                        "Evidence: " + ", ".join(report_section.evidence_references)
                    )

            for diagram in report.diagrams:
                document.add_heading(redact_sensitive_text(diagram.title), level=1)
                if report.configuration.include_rendered_diagrams and diagram.rendered_png:
                    try:
                        document.add_picture(BytesIO(diagram.rendered_png), width=None)
                    except Exception:
                        pass
                if report.configuration.include_mermaid_source:
                    document.add_paragraph("Mermaid source fallback:")
                    document.add_paragraph(redact_sensitive_text(diagram.mermaid_source))
                if report.configuration.include_evidence and diagram.evidence_references:
                    document.add_paragraph("Evidence: " + ", ".join(diagram.evidence_references))

            buffer = BytesIO()
            document.save(buffer)
            content = buffer.getvalue()
        except Exception as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.docx,
                output_file_name=manager.safe_filename(report.report_id, "docx"),
                export_status="failed",
                warnings=[f"DOCX export failed: {type(exc).__name__}."],
            )

        try:
            _, relative, size = manager.write_bytes(report.report_id, "docx", content)
        except (OSError, ValueError) as exc:
            return ReportExportResult(
                report_id=report.report_id,
                output_format=ReportFormat.docx,
                output_file_name=manager.safe_filename(report.report_id, "docx"),
                export_status="failed",
                warnings=[f"DOCX artifact write failed: {type(exc).__name__}."],
            )
        return ReportExportResult(
            report_id=report.report_id,
            output_format=ReportFormat.docx,
            output_file_name=Path(relative).name,
            managed_artifact_reference=relative,
            file_size=size,
            export_status="completed",
        )
