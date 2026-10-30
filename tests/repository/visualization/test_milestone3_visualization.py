from uuid import uuid4
import subprocess

from app.repository.analysis.models import (
    ApiEndpointFinding,
    ArchitecturePatternFinding,
    ConfidenceLevel,
    DatabaseFinding,
    DependencyFinding,
    EvidenceCategory,
    EvidenceReference,
    IntegrationFinding,
    ProjectFinding,
    ProjectStructureFinding,
    RepositoryAnalysisResult,
    TechnologyFinding,
)
from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
from app.repository.visualization.diagram_generator import DiagramGenerator
from app.repository.visualization.diagram_renderer import DiagramRenderer
from app.repository.visualization.diagram_validator import DiagramValidator
from app.repository.visualization.evidence_mapper import EvidenceMapper
from app.repository.visualization.models import DiagramType


def analysis_fixture() -> RepositoryAnalysisResult:
    evidence = [
        EvidenceReference(
            evidence_id="E0001",
            relative_path="src/Web.csproj",
            category=EvidenceCategory.project,
            explanation="ASP.NET project declaration.",
        ),
        EvidenceReference(
            evidence_id="E0002",
            relative_path="src/Program.cs",
            category=EvidenceCategory.api,
            explanation="API route declaration.",
        ),
        EvidenceReference(
            evidence_id="E0003",
            relative_path="src/database.py",
            category=EvidenceCategory.database,
            explanation="Database configuration.",
        ),
        EvidenceReference(
            evidence_id="E0004",
            relative_path="src/client.py",
            category=EvidenceCategory.integration,
            explanation="External integration package usage.",
        ),
    ]
    return RepositoryAnalysisResult(
        analysis_id=uuid4(),
        repository_name="Safe Sample",
        source_type="local",
        source_reference="sample",
        technology_stack=[
            TechnologyFinding(
                name="ASP.NET Core",
                category="framework",
                evidence_references=["E0001"],
                confidence=ConfidenceLevel.high,
            )
        ],
        projects=[
            ProjectFinding(
                name="Web API",
                relative_path="src/Web.csproj",
                kind="project",
                evidence_references=["E0001"],
            )
        ],
        project_structure=ProjectStructureFinding(summary="A backend project was detected."),
        dependencies=[
            DependencyFinding(
                source="src/Program.cs",
                target="src/database.py",
                dependency_type="imports",
                resolved=True,
                evidence_references=["E0002", "E0003"],
            )
        ],
        api_endpoints=[
            ApiEndpointFinding(
                exposure="exposed",
                method="GET",
                route="/api/items",
                relative_path="src/Program.cs",
                framework="ASP.NET Core",
                evidence_references=["E0002"],
            ),
            ApiEndpointFinding(
                exposure="consumed",
                method="GET",
                route="/external/items",
                relative_path="src/client.py",
                framework="HTTP",
                evidence_references=["E0004"],
            ),
        ],
        database_findings=[
            DatabaseFinding(
                technology="SQL Server",
                evidence_type="ORM",
                relative_path="src/database.py",
                detail="Entity Framework configuration",
                evidence_references=["E0003"],
            )
        ],
        external_integrations=[
            IntegrationFinding(
                name="Payments Service",
                integration_type="REST API",
                status="confirmed",
                relative_path="src/client.py",
                detail="HTTP client evidence",
                evidence_references=["E0004"],
            )
        ],
        architectural_patterns=[
            ArchitecturePatternFinding(
                name="Layered Architecture",
                evidence=["Layered directories were identified."],
                relevant_files=["src/Program.cs"],
                explanation="Static project structure supports a layered organization.",
                confidence=ConfidenceLevel.high,
                limitations="Runtime topology is not observed.",
            )
        ],
        evidence=evidence,
        summary="A mixed static architecture finding sample.",
    )


def test_all_supported_diagram_types_are_generated() -> None:
    analysis = analysis_fixture()
    diagrams = DiagramGenerator().generate(analysis)

    assert {diagram.diagram_type for diagram in diagrams} == set(DiagramType)
    assert all(diagram.mermaid_source.startswith("flowchart ") for diagram in diagrams)
    assert len({diagram.diagram_id for diagram in diagrams}) == len(diagrams)
    for diagram in diagrams:
        assert all(
            evidence.evidence_id in {item.evidence_id for item in analysis.evidence}
            for evidence in [
                evidence
                for node in diagram.nodes
                for evidence in node.evidence_references
            ]
        )


def test_diagram_validator_accepts_generated_diagrams_and_evidence() -> None:
    analysis = analysis_fixture()
    generator = DiagramGenerator()
    validator = DiagramValidator()

    for diagram in generator.generate(analysis):
        result = validator.validate(diagram, analysis)
        assert result.valid, result.errors


def test_visualizer_preserves_mermaid_source_when_renderer_is_unavailable() -> None:
    renderer = DiagramRenderer(executable_path=r"C:\does-not-exist\mmdc.exe")
    result = ArchitectureVisualizer(diagram_renderer=renderer).visualize(analysis_fixture())

    assert all(diagram.mermaid_source for diagram in result.diagrams)
    assert result.visualization_warnings
    assert result.generation_metadata.renderer_name == "mermaid-source"


def test_evidence_mapper_returns_only_existing_relative_evidence() -> None:
    analysis = analysis_fixture()
    mapped = EvidenceMapper().map_evidence(analysis, ["E0002", "missing", "E0002"])

    assert [item.evidence_id for item in mapped] == ["E0002"]
    assert mapped[0].relative_path == "src/Program.cs"


def test_renderer_returns_svg_and_png_from_a_mocked_local_mermaid_cli(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "mmdc.exe"
    executable.write_text("mock executable", encoding="utf-8")

    def fake_run(command, **kwargs):
        output_path = command[command.index("-o") + 1]
        if output_path.endswith(".svg"):
            open(output_path, "w", encoding="utf-8").write("<svg><rect/></svg>")
        else:
            open(output_path, "wb").write(b"\x89PNG\r\n\x1a\nmock")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("app.repository.visualization.diagram_renderer.subprocess.run", fake_run)
    renderer = DiagramRenderer(executable_path=str(executable))

    svg = renderer.render_svg("flowchart LR\napp[Application]")
    png = renderer.render_png("flowchart LR\napp[Application]")

    assert svg == "<svg><rect/></svg>"
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
