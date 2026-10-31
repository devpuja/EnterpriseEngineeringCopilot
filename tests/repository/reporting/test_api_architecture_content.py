from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.repository.analysis.api_analyzer import APIAnalyzer
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.models import RepositoryFile, RepositorySnapshot
from app.repository.reporting.exporters import DOCXExporter, HTMLExporter, MarkdownExporter, PDFExporter
from app.repository.reporting.exporters.base import redact_sensitive_text
from app.repository.reporting.models import ReportConfiguration
from app.repository.reporting.report_generator import ReportGenerator
from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
from app.repository.visualization.diagram_validator import DiagramValidator
from tests.repository.visualization.test_milestone3_visualization import analysis_fixture


def analyze_files(files):
    snapshot = RepositorySnapshot(
        source_type="github",
        repository_name="Agents",
        source_reference="https://github.com/devpuja/Agents/tree/main/agent-project",
        workspace_id=uuid4(),
        files=[
            RepositoryFile(
                relative_path=name, file_name=Path(name).name,
                extension=Path(name).suffix, size_bytes=len(text),
                is_binary=name.endswith(".bin"),
            )
            for name, text in files.items()
        ],
        total_files=len(files),
        total_size_bytes=sum(len(text) for text in files.values()),
    )
    reader = Mock()
    reader.read_text.side_effect = lambda snapshot, file: files[file.relative_path]
    evidence = EvidenceCollector()
    endpoints = APIAnalyzer().analyze(snapshot, reader, evidence)
    return endpoints, evidence, reader


def test_api_analyzer_ignores_pdf_text_and_database_fetchall():
    endpoints, _, reader = analyze_files({
        "app.py": '@app.post("/chat")\ndef chat(): pass\n@app.post("/upload")\ndef upload(): pass',
        "services/sqlite_service.py": "return cursor.fetchall()\nreturn cursor.fetchall()",
        "documents/handbook.pdf": "fetch axios.get('/api/not-real')",
        "README.md": "fetch('/example')",
        "data.bin": "fetch('/binary')",
    })
    assert {(item.exposure, item.method, item.route) for item in endpoints} == {
        ("exposed", "POST", "/chat"), ("exposed", "POST", "/upload"),
    }
    assert {call.args[1].relative_path for call in reader.read_text.call_args_list} == {
        "app.py", "services/sqlite_service.py",
    }


def test_http_client_calls_use_call_arguments_and_explicit_methods():
    endpoints, _, _ = analyze_files({
        "client.ts": (
            'fetch("/chat", {method: "POST"});\n'
            'axios.get("/items");\n'
            'axios.post("https://example.com/v1/upload");\n'
            'fetch(dynamicUrl);\n'
            '// fetch("/not-a-call");\n'
            'cursor.fetchall();\n'
        ),
    })
    assert [(item.method, item.route) for item in endpoints] == [
        ("POST", "/chat"), ("GET", "/items"),
        ("POST", "https://example.com/v1/upload"), ("GET", "unknown"),
    ]
    assert all(item.exposure == "consumed" for item in endpoints)


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def test_http_route_context_is_preserved_without_exempting_local_paths(method):
    text = f'{method} /api/items/{{id}} from /home/user/private.txt and C:\\private\\repo'
    result = redact_sensitive_text(text)
    assert f"{method} /api/items/{{id}}" in result
    assert "/home/user" not in result
    assert "C:\\private" not in result
    assert redact_sensitive_text(f"api:{method}:/chat") == f"api:{method}:/chat"
    assert "secret-value" not in redact_sensitive_text(f"{method} /chat?token=secret-value")


def test_redacting_path_in_mermaid_preserves_node_syntax():
    source = 'flowchart LR\n    n["/home/user/private.txt"]'
    assert redact_sensitive_text(source) == 'flowchart LR\n    n["[LOCAL PATH WITHHELD]"]'


@pytest.mark.parametrize("exporter", [
    MarkdownExporter(), HTMLExporter(), PDFExporter(), DOCXExporter(),
])
def test_exact_api_endpoint_content_survives_report_and_every_export(tmp_path, exporter):
    endpoints, _, _ = analyze_files({
        "app.py": '@app.post("/chat")\ndef chat(): pass\n@app.post("/upload")\ndef upload(): pass',
        "client.ts": 'fetch("/chat", {method: "POST"});',
    })
    analysis = analysis_fixture()
    analysis.source_type = "github"
    analysis.source_reference = "https://github.com/devpuja/Agents/tree/main/agent-project"
    analysis.api_endpoints = endpoints
    for item in endpoints:
        item.evidence_references = []
    report = ReportGenerator().generate(
        analysis, ArchitectureVisualizer().visualize(analysis),
        ReportConfiguration(
            selected_diagram_types=["api"], include_sections=["api_architecture"],
        ),
    )
    section = next(item for item in report.sections if item.section_id == "api_architecture")
    assert section.content.startswith(
        "Exposed APIs:\n- POST /chat (FastAPI)\n- POST /upload (FastAPI)\n"
        "Consumed APIs:\n- POST /chat (HTTP client)"
    )
    assert "SDK-based and dynamically constructed API calls may not be detected." in section.content
    diagram = report.diagrams[0]
    assert "POST /chat" in diagram.mermaid_source
    assert "POST /upload" in diagram.mermaid_source
    assert DiagramValidator().validate(diagram, analysis).valid
    for relationship in diagram.relationships:
        assert relationship.source_node_id != relationship.target_node_id
        assert (
            f"{relationship.source_node_id} -->|{relationship.relationship_type}| "
            f"{relationship.target_node_id}"
        ) in diagram.mermaid_source
    result = exporter.export(report, tmp_path)
    assert result.export_status == "completed", result.warnings
    path = tmp_path / result.managed_artifact_reference
    if path.suffix == ".pdf":
        from pypdf import PdfReader
        content = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    elif path.suffix == ".docx":
        from docx import Document
        content = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    else:
        content = path.read_text(encoding="utf-8")
    assert "Exposed APIs:" in content
    assert "POST /chat" in content
    assert "POST /upload" in content
    assert "GET unknown" not in content
    assert "[LOCAL PATH WITHHELD]" not in section.content
