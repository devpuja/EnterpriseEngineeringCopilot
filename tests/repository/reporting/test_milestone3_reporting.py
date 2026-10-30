from pathlib import Path
import zipfile

from app.repository.reporting.artifact_manager import ArtifactManager
from app.repository.reporting.exporters.docx_exporter import DOCXExporter
from app.repository.reporting.exporters.html_exporter import HTMLExporter
from app.repository.reporting.exporters.markdown_exporter import MarkdownExporter
from app.repository.reporting.exporters.pdf_exporter import PDFExporter
from app.repository.reporting.models import ReportConfiguration, ReportFormat
from app.repository.reporting.report_generator import ReportGenerator
from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
from tests.repository.visualization.test_milestone3_visualization import analysis_fixture


def report_fixture():
    analysis = analysis_fixture()
    visualization = ArchitectureVisualizer().visualize(analysis)
    report = ReportGenerator().generate(
        analysis,
        visualization,
        ReportConfiguration(
            title="Architecture Report <script>alert('x')</script>",
            organization_name="Engineering",
        ),
    )
    return report


def test_report_generator_creates_structured_sections_and_visualization_links():
    report = report_fixture()

    assert report.sections
    section_ids = {section.section_id for section in report.sections}
    assert {
        "cover",
        "executive_summary",
        "repository_overview",
        "architecture_diagrams",
        "limitations",
        "evidence_references",
        "appendix",
    } <= section_ids
    assert report.diagrams
    assert report.title.startswith("Architecture Report")


def test_markdown_and_html_exports_are_safe_and_manage_artifacts(tmp_path):
    report = report_fixture()
    report_dir = tmp_path / "artifacts"
    markdown = MarkdownExporter().export(report, report_dir)
    html = HTMLExporter().export(report, report_dir)

    assert markdown.export_status == "completed"
    assert html.export_status == "completed"
    artifact_root = (report_dir / str(report.report_id)).resolve()
    markdown_file = artifact_root / markdown.output_file_name
    html_file = artifact_root / html.output_file_name
    assert markdown_file.is_file()
    assert html_file.is_file()
    assert "<script>" not in html_file.read_text(encoding="utf-8")
    assert "<script" not in html_file.read_text(encoding="utf-8")
    assert markdown_file.read_text(encoding="utf-8").startswith("# ")
    assert ".." not in markdown.managed_artifact_reference
    assert not Path(markdown.managed_artifact_reference).is_absolute()


def test_pdf_and_docx_exports_are_valid(tmp_path):
    report = report_fixture()
    pdf_result = PDFExporter().export(report, tmp_path / "pdf")
    docx_result = DOCXExporter().export(report, tmp_path / "docx")

    assert pdf_result.export_status == "completed"
    assert docx_result.export_status == "completed"
    pdf_file = tmp_path / "pdf" / str(report.report_id) / pdf_result.output_file_name
    docx_file = tmp_path / "docx" / str(report.report_id) / docx_result.output_file_name
    assert pdf_file.read_bytes().startswith(b"%PDF-")
    assert docx_file.is_file()
    assert zipfile.is_zipfile(docx_file)
    with zipfile.ZipFile(docx_file) as archive:
        assert "[Content_Types].xml" in archive.namelist()
        assert "word/document.xml" in archive.namelist()


def test_artifact_manager_rejects_traversal_and_prevents_overwrite(tmp_path):
    manager = ArtifactManager(tmp_path / "managed")
    report_id = report_fixture().report_id
    _, relative, size = manager.write_text(report_id, "md", "# Report")

    assert relative.startswith(str(report_id) + "/")
    assert size > 0
    try:
        manager.write_text(report_id, "md", "# Replacement")
        raise AssertionError("Expected overwrite prevention")
    except FileExistsError:
        pass

    try:
        manager.safe_filename(report_id, "../html")
        raise AssertionError("Expected unsupported extension rejection")
    except ValueError:
        pass


def test_artifact_cleanup_is_isolated(tmp_path):
    manager = ArtifactManager(tmp_path / "managed")
    report_id = report_fixture().report_id
    manager.write_text(report_id, "md", "# Report")

    assert manager.cleanup_report(report_id) is True
    assert not (tmp_path / "managed" / str(report_id)).exists()
