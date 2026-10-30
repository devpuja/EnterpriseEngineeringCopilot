from pathlib import Path
import zipfile
import base64
import pytest

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


ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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


def test_rendered_diagram_embedding_and_mermaid_fallback(tmp_path):
    report = report_fixture()
    for diagram in report.diagrams:
        diagram.rendered_png = ONE_PIXEL_PNG
        diagram.rendered_svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"10\" height=\"10\"/><script>alert(1)</script></svg>"

    html_result = HTMLExporter().export(report, tmp_path / "html")
    pdf_result = PDFExporter().export(report, tmp_path / "pdf")
    docx_result = DOCXExporter().export(report, tmp_path / "docx")
    assert html_result.export_status == "completed"
    assert pdf_result.export_status == "completed"
    assert docx_result.export_status == "completed"

    html_file = tmp_path / "html" / str(report.report_id) / html_result.output_file_name
    html_text = html_file.read_text(encoding="utf-8")
    assert "data:image/png;base64," not in html_text
    assert "data:image/svg+xml;base64," in html_text
    assert "<script" not in html_text

    pdf_file = tmp_path / "pdf" / str(report.report_id) / pdf_result.output_file_name
    pdf_bytes = pdf_file.read_bytes()
    assert b"/Subtype /Image" in pdf_bytes

    docx_file = tmp_path / "docx" / str(report.report_id) / docx_result.output_file_name
    with zipfile.ZipFile(docx_file) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        document_xml = archive.read("word/document.xml")
        assert media
        assert b"Mermaid source fallback:" in document_xml


@pytest.mark.parametrize(
    ("configuration", "expected_diagram_count", "expect_evidence", "expect_confidence", "expect_limitations", "expect_mermaid"),
    [
        (
            ReportConfiguration(
                include_evidence=False,
                include_confidence=False,
                include_limitations=False,
                include_mermaid_source=False,
                include_rendered_diagrams=False,
            ),
            7,
            False,
            False,
            False,
            False,
        ),
        (
            ReportConfiguration(
                selected_diagram_types=["api"],
                include_sections=["architecture_diagrams", "api_architecture"],
                exclude_sections=[],
                include_evidence=True,
                include_confidence=True,
                include_limitations=True,
                include_mermaid_source=True,
                include_rendered_diagrams=True,
            ),
            1,
            True,
            True,
            True,
            True,
        ),
    ],
)
def test_report_configuration_combinations(
    tmp_path,
    configuration,
    expected_diagram_count,
    expect_evidence,
    expect_confidence,
    expect_limitations,
    expect_mermaid,
):
    analysis = analysis_fixture()
    analysis.repository_name = "Repo & <Name> >"
    visualization = ArchitectureVisualizer().visualize(analysis)
    report = ReportGenerator().generate(analysis, visualization, configuration)

    assert len(report.diagrams) == expected_diagram_count
    section_ids = {section.section_id for section in report.sections}
    assert ("limitations" in section_ids) is expect_limitations
    assert ("evidence_references" in section_ids) is expect_evidence
    if configuration.selected_diagram_types:
        assert all(section.related_diagram_ids == [
            diagram_id
            for diagram_id in section.related_diagram_ids
            if diagram_id == "api_architecture"
        ] for section in report.sections if section.related_diagram_ids)
    if not configuration.include_confidence:
        serialized = report.model_dump_json()
        assert "high)" not in serialized
        assert "confidence" not in serialized.lower()
    assert all(
        diagram.diagram_id
        for diagram in report.diagrams
    )

    markdown = MarkdownExporter().export(report, tmp_path / "md")
    html = HTMLExporter().export(report, tmp_path / "html")
    pdf = PDFExporter().export(report, tmp_path / "pdf")
    docx = DOCXExporter().export(report, tmp_path / "docx")
    assert all(result.export_status == "completed" for result in (markdown, html, pdf, docx))

    md_text = (tmp_path / "md" / str(report.report_id) / markdown.output_file_name).read_text(encoding="utf-8")
    html_text = (tmp_path / "html" / str(report.report_id) / html.output_file_name).read_text(encoding="utf-8")
    assert ("```mermaid" in md_text) is expect_mermaid
    assert ("<code>" in html_text or "flowchart LR" in html_text) is expect_mermaid


def test_pdf_safe_escaping_for_untrusted_repository_text(tmp_path):
    analysis = analysis_fixture()
    analysis.repository_name = "Repo & <unsafe> > name"
    analysis.summary = "Description <b>not markup</b> & untrusted > text"
    visualization = ArchitectureVisualizer().visualize(analysis)
    report = ReportGenerator().generate(analysis, visualization)

    result = PDFExporter().export(report, tmp_path / "pdf")
    assert result.export_status == "completed"
    output = tmp_path / "pdf" / str(report.report_id) / result.output_file_name
    assert output.read_bytes().startswith(b"%PDF-")
