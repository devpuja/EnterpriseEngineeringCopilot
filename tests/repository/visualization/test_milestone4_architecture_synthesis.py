from uuid import uuid4

from app.repository.analysis.models import (
    ApiEndpointFinding,
    ConfidenceLevel,
    DatabaseFinding,
    EvidenceCategory,
    EvidenceReference,
    IntegrationFinding,
    ProjectFinding,
    ProjectStructureFinding,
    RepositoryAnalysisResult,
)
from app.repository.synthesis import ArchitectureSynthesizer
from app.repository.visualization.diagram_validator import DiagramValidator


def representative_analysis(*, repository_name: str = "Representative Repository", include_incomplete: bool = False) -> RepositoryAnalysisResult:
    evidence = [
        EvidenceReference(
            evidence_id="E001",
            relative_path="src/Api.csproj",
            category=EvidenceCategory.project,
            explanation="Web project declaration.",
            confidence=ConfidenceLevel.high,
        ),
        EvidenceReference(
            evidence_id="E002",
            relative_path="src/Program.cs",
            category=EvidenceCategory.api,
            explanation="Exposed route declaration.",
            confidence=ConfidenceLevel.high,
        ),
        EvidenceReference(
            evidence_id="E003",
            relative_path="src/database.py",
            category=EvidenceCategory.database,
            explanation="Database configuration.",
            confidence=ConfidenceLevel.medium,
        ),
        EvidenceReference(
            evidence_id="E004",
            relative_path="src/payments.py",
            category=EvidenceCategory.integration,
            explanation="Payment service integration.",
            confidence=ConfidenceLevel.medium,
        ),
    ]
    return RepositoryAnalysisResult(
        analysis_id=uuid4(),
        repository_name=repository_name,
        source_type="local",
        source_reference="fixture",
        projects=[
            ProjectFinding(
                name="Api" if repository_name != "bad ] [ name\n<script>" else "Api",
                relative_path="src/Api.csproj",
                kind="project",
                evidence_references=["E001"],
                confidence=ConfidenceLevel.high,
            )
        ],
        project_structure=ProjectStructureFinding(summary="Static project structure."),
        api_endpoints=[] if include_incomplete else [
            ApiEndpointFinding(
                exposure="exposed",
                method="GET",
                route="/api/items",
                relative_path="src/Program.cs",
                framework="ASP.NET Core",
                evidence_references=["E002"],
                confidence=ConfidenceLevel.high,
            )
        ],
        database_findings=[] if include_incomplete else [
            DatabaseFinding(
                technology="PostgreSQL",
                evidence_type="configuration",
                relative_path="src/database.py",
                detail="Connection configuration evidence.",
                evidence_references=["E003"],
                confidence=ConfidenceLevel.medium,
            )
        ],
        external_integrations=[] if include_incomplete else [
            IntegrationFinding(
                name="Payments Service",
                integration_type="REST API",
                status="confirmed",
                relative_path="src/payments.py",
                detail="HTTP client evidence.",
                evidence_references=["E004"],
                confidence=ConfidenceLevel.medium,
            )
        ],
        evidence=evidence,
        analysis_warnings=["Static analysis is partial"] if include_incomplete else [],
        limitations=["Runtime behavior was not observed."],
        summary="Representative static analysis.",
    )


def test_dotnet_style_synthesis_has_components_relationships_and_evidence():
    analysis = representative_analysis(repository_name="Payments API")
    synthesis = ArchitectureSynthesizer().synthesize(analysis)

    assert synthesis.original_analysis_id == analysis.analysis_id
    assert {component.component_type for component in synthesis.components} >= {"repository", "project"}
    assert any(component.component_type == "api_boundary" for component in synthesis.components)
    assert any(component.component_type == "persistence" for component in synthesis.components)
    assert synthesis.external_systems
    assert all(
        evidence_id in {e.evidence_id for e in analysis.evidence}
        for item in synthesis.components
        for evidence_id in item.evidence_references
    )
    assert "runtime" in synthesis.architecture_summary.lower()


def test_python_style_synthesis_and_confirmed_inferred_relationships():
    analysis = representative_analysis(repository_name="Python Service")
    synthesis = ArchitectureSynthesizer().synthesize(analysis)

    assert synthesis.data_flows
    assert any(flow.status.value == "confirmed" for flow in synthesis.data_flows)
    assert any("No runtime" in value or "runtime" in value.lower() for value in [
        synthesis.architecture_summary, *synthesis.warnings, *synthesis.limitations
    ])

    # Mutate a dependency into unresolved/inferred evidence without inventing runtime behavior.
    from app.repository.analysis.models import DependencyFinding
    analysis.dependencies = [
        DependencyFinding(
            source="src/unknown.py",
            target="src/Api.csproj",
            dependency_type="imports",
            resolved=False,
            evidence_references=["E001"],
            confidence=ConfidenceLevel.low,
        )
    ]
    inferred = ArchitectureSynthesizer().synthesize(analysis)
    assert any(
        relationship.status.value == "inferred"
        for relationship in inferred.relationships
    )


def test_mermaid_is_stable_safe_validated_and_complexity_limited():
    analysis = representative_analysis(repository_name='bad ] [ name\n<script>alert(1)</script>|x')
    synthesis = ArchitectureSynthesizer(maximum_nodes=4, maximum_edges=4).synthesize(analysis)
    diagram = synthesis.unified_diagram

    assert diagram is not None
    assert diagram.mermaid_source.startswith("flowchart LR")
    assert "<script>" not in diagram.mermaid_source
    assert "|" not in "".join(diagram.mermaid_source.split("|")[:1])
    assert len({node.node_id for node in diagram.nodes}) == len(diagram.nodes)
    assert len(diagram.nodes) <= 4
    assert len(diagram.relationships) <= 4
    assert DiagramValidator(maximum_nodes=4, maximum_edges=4).validate(diagram, analysis).valid
    repeat = ArchitectureSynthesizer(maximum_nodes=4, maximum_edges=4).synthesize(analysis)
    assert [item.component_id for item in synthesis.components] == [
        item.component_id for item in repeat.components
    ]


def test_incomplete_analysis_returns_warning_without_inventing_components():
    synthesis = ArchitectureSynthesizer().synthesize(
        representative_analysis(repository_name="Empty Service", include_incomplete=True)
    )

    assert synthesis.warnings
    assert synthesis.components
    assert synthesis.external_systems == []
    assert synthesis.data_flows == []
    assert "No runtime" in synthesis.architecture_summary or "runtime" in synthesis.architecture_summary.lower()
