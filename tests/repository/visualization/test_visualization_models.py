from uuid import uuid4

from app.repository.analysis.models import (
    ConfidenceLevel,
    EvidenceCategory,
    ProjectStructureFinding,
    RepositoryAnalysisResult,
)
from app.repository.reporting.models import (
    ArchitectureReport,
    ReportConfiguration,
    ReportExportResult,
    ReportFormat,
    ReportMetadata,
    ReportSection,
)
from app.repository.visualization.models import (
    ArchitectureDiagram,
    ArchitectureVisualizationResult,
    DiagramEvidenceReference,
    DiagramGenerationMetadata,
    DiagramType,
)


def inconclusive_analysis() -> RepositoryAnalysisResult:
    analysis_id = uuid4()
    return RepositoryAnalysisResult(
        analysis_id=analysis_id,
        repository_name="sample",
        source_type="local",
        source_reference="/safe/repository/entry",
        project_structure=ProjectStructureFinding(summary="No supported structure determined."),
        summary="Static analysis produced no specific architecture findings.",
        limitations=["Static analysis only."],
    )


def test_visualization_models_accept_repository_analysis_result() -> None:
    analysis = inconclusive_analysis()
    diagram = ArchitectureDiagram(
        diagram_id="system_context",
        title="System Context",
        diagram_type=DiagramType.system_context,
        description="A high-level view.",
        mermaid_source='flowchart LR\napp["Application"]',
        generation_warnings=["Limited evidence"],
    )
    result = ArchitectureVisualizationResult(
        analysis_id=analysis.analysis_id,
        repository_name=analysis.repository_name,
        diagrams=[diagram],
        generation_metadata=DiagramGenerationMetadata(generated_at="2026-01-01T00:00:00Z"),
    )

    assert result.analysis_id == analysis.analysis_id
    assert result.diagrams[0].diagram_type == DiagramType.system_context


def test_evidence_reference_preserves_relative_path_and_metadata() -> None:
    evidence = DiagramEvidenceReference(
        evidence_id="E0001",
        relative_path="src/app.py",
        category=EvidenceCategory.technology,
        confidence=ConfidenceLevel.medium,
        finding_id="technology-1",
        explanation="Detected Python source.",
    )

    assert evidence.relative_path == "src/app.py"
    assert evidence.line_number is None
    assert evidence.line_end is None


def test_report_models_share_diagrams_and_export_contract_shape() -> None:
    analysis = inconclusive_analysis()
    diagram = ArchitectureDiagram(
        diagram_id="component",
        title="Components",
        diagram_type=DiagramType.component,
        description="No supported components identified.",
        mermaid_source='flowchart LR\napp["Application"]',
    )
    report = ArchitectureReport(
        analysis_id=analysis.analysis_id,
        repository_name=analysis.repository_name,
        title="Architecture Report",
        sections=[
            ReportSection(
                section_id="limitations",
                title="Limitations and unknowns",
                content="No supported architecture findings were identified.",
            )
        ],
        diagrams=[diagram],
        report_metadata=ReportMetadata(generated_at="2026-01-01T00:00:00Z"),
        limitations=analysis.limitations,
    )
    export = ReportExportResult(
        report_id=report.report_id,
        output_format=ReportFormat.markdown,
        output_file_name="architecture-report.md",
        managed_artifact_reference="reports/sample/architecture-report.md",
        file_size=128,
        export_status="completed",
    )
    configuration = ReportConfiguration(title="Architecture Report")

    assert report.diagrams[0].diagram_id == diagram.diagram_id
    assert export.output_format == ReportFormat.markdown
    assert configuration.include_evidence is True
