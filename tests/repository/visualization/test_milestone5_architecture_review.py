from uuid import uuid4

from app.repository.analysis.models import ConfidenceLevel, DependencyFinding, EvidenceCategory, EvidenceReference, RepositoryAnalysisResult, ProjectStructureFinding
from app.repository.review import ArchitectureReviewFindingStatus, ArchitectureReviewOutcome, ArchitectureReviewService
from app.repository.synthesis.models import (
    ArchitectureComponent,
    ArchitectureDataFlow,
    ArchitectureRelationship,
    ArchitectureSynthesisMetadata,
    ArchitectureSynthesisResult,
    ExternalSystem,
    RelationshipStatus,
)


def synthesis(
    *,
    components: list[ArchitectureComponent] | None = None,
    relationships: list[ArchitectureRelationship] | None = None,
    data_flows: list[ArchitectureDataFlow] | None = None,
    external_systems: list[ExternalSystem] | None = None,
) -> ArchitectureSynthesisResult:
    analysis_id = uuid4()
    return ArchitectureSynthesisResult(
        synthesis_id=uuid4(),
        original_analysis_id=analysis_id,
        repository_name="Review Fixture",
        components=components or [],
        relationships=relationships or [],
        data_flows=data_flows or [],
        external_systems=external_systems or [],
        architecture_summary="Static synthesis fixture.",
        warnings=[],
        limitations=["No runtime behavior was observed."],
        synthesis_metadata=ArchitectureSynthesisMetadata(synthesis_generated_at="2026-01-01T00:00:00+00:00"),
    )


def evidence():
    return EvidenceReference(
        evidence_id="EV1",
        relative_path="src/service.py",
        category=EvidenceCategory.dependency,
        explanation="Dependency evidence.",
        confidence=ConfidenceLevel.high,
    )


def representative_synthesis():
    components = [
        ArchitectureComponent(
            component_id="repository_repo",
            name="Review Fixture",
            component_type="repository",
            description="Repository application boundary represented by static analysis findings.",
            evidence_references=["EV1"],
            confidence=ConfidenceLevel.high,
        ),
        ArchitectureComponent(
            component_id="project_api",
            name="API",
            component_type="project",
            description="API project responsible for request handling and application endpoints.",
            evidence_references=["EV1"],
            confidence=ConfidenceLevel.high,
        ),
    ]
    relationships = [
        ArchitectureRelationship(
            source_component_id="repository_repo",
            target_component_id="project_api",
            relationship_type="contains",
            description="Repository contains the API project.",
            evidence_references=["EV1"],
            status=RelationshipStatus.confirmed,
            confidence=ConfidenceLevel.high,
        )
    ]
    data_flows = [
        ArchitectureDataFlow(
            source_component_id="repository_repo",
            target_component_id="project_api",
            flow_description="Static evidence identifies a project interaction.",
            evidence_references=["EV1"],
            status=RelationshipStatus.confirmed,
            confidence=ConfidenceLevel.high,
        )
    ]
    return synthesis(components=components, relationships=relationships, data_flows=data_flows)


def test_dotnet_and_python_style_synthesis_reviews_are_structured():
    review = ArchitectureReviewService().review(representative_synthesis())
    assert review.original_synthesis_id == review.original_synthesis_id
    assert review.repository_name == "Review Fixture"
    assert review.findings or review.strengths
    assert all(finding.evidence_references == sorted(set(finding.evidence_references)) for finding in review.findings)


def test_confirmed_inferred_and_investigation_statuses_are_distinct():
    unresolved = ArchitectureRelationship(
        source_component_id="A",
        target_component_id="B",
        relationship_type="imports",
        description="Unresolved static dependency.",
        evidence_references=["EV1"],
        status=RelationshipStatus.inferred,
        confidence=ConfidenceLevel.low,
    )
    result = synthesis(
        components=[
            ArchitectureComponent(component_id="A", name="A", component_type="project", description="A service with a clearly stated responsibility.", evidence_references=["EV1"]),
            ArchitectureComponent(component_id="B", name="B", component_type="project", description="A service with a clearly stated responsibility.", evidence_references=["EV1"]),
        ],
        relationships=[unresolved],
    )
    review = ArchitectureReviewService().review(result)
    assert any(f.status == ArchitectureReviewFindingStatus.inferred for f in review.findings)

    empty = ArchitectureReviewService().review(synthesis())
    assert any(f.status == ArchitectureReviewFindingStatus.needs_investigation for f in empty.findings)


def test_unresolved_dependency_and_evidence_traceability():
    result = representative_synthesis()
    result.relationships.append(ArchitectureRelationship(
        source_component_id="repository_repo",
        target_component_id="project_api",
        relationship_type="imports",
        description="Unresolved dependency from src/unknown.py to API project.",
        evidence_references=["EV1"],
        status=RelationshipStatus.inferred,
        confidence=ConfidenceLevel.low,
    ))
    review = ArchitectureReviewService().review(result)
    unresolved = [finding for finding in review.findings if finding.rule_id == "DEP-001"]
    assert unresolved
    assert all(finding.evidence_references for finding in unresolved)


def test_dep001_only_evaluates_dependency_relationship_types():
    dependency = ArchitectureRelationship(
        source_component_id="A",
        target_component_id="B",
        relationship_type="imports",
        description="Unresolved static dependency.",
        evidence_references=["EV1"],
        status=RelationshipStatus.inferred,
    )
    integration = ArchitectureRelationship(
        source_component_id="A",
        target_component_id="external_payments",
        relationship_type="integrates_with",
        description="Inferred external integration.",
        evidence_references=["EV1"],
        status=RelationshipStatus.inferred,
    )
    structural = ArchitectureRelationship(
        source_component_id="A",
        target_component_id="B",
        relationship_type="contains",
        description="Inferred repository containment.",
        evidence_references=["EV1"],
        status=RelationshipStatus.inferred,
    )
    result = synthesis(components=[
        ArchitectureComponent(
            component_id="A",
            name="A",
            component_type="project",
            description="A project with a clearly stated responsibility.",
            evidence_references=["EV1"],
        ),
        ArchitectureComponent(
            component_id="B",
            name="B",
            component_type="project",
            description="A project with a clearly stated responsibility.",
            evidence_references=["EV1"],
        ),
    ], relationships=[dependency, integration, structural])

    review = ArchitectureReviewService().review(result)
    dep001_relationships = [
        finding.related_relationships[0]
        for finding in review.findings
        if finding.rule_id == "DEP-001"
    ]
    assert any("imports" in relationship for relationship in dep001_relationships)
    assert all("integrates_with" not in relationship for relationship in dep001_relationships)
    assert all("contains" not in relationship for relationship in dep001_relationships)


def test_matching_analysis_makes_evidence_ids_authoritative():
    result = representative_synthesis()
    result.relationships.append(ArchitectureRelationship(
        source_component_id="repository_repo",
        target_component_id="project_api",
        relationship_type="project_reference",
        description="Unresolved dependency.",
        evidence_references=["EV2"],
        status=RelationshipStatus.inferred,
        confidence=ConfidenceLevel.low,
    ))
    matching_analysis = RepositoryAnalysisResult(
        analysis_id=result.original_analysis_id,
        repository_name=result.repository_name,
        source_type="local",
        source_reference="fixture",
        project_structure=ProjectStructureFinding(summary="Fixture structure."),
        evidence=[evidence()],
        summary="Fixture analysis.",
    )
    review = ArchitectureReviewService().review(result, matching_analysis)

    dep001 = [finding for finding in review.findings if finding.rule_id == "DEP-001"]
    invalid_dependency_finding = next(
        finding for finding in dep001
        if "project_reference" in finding.related_relationships[0]
    )
    assert invalid_dependency_finding.status == ArchitectureReviewFindingStatus.needs_investigation
    assert invalid_dependency_finding.evidence_references == []
    assert "EV2" not in invalid_dependency_finding.evidence_references


def test_present_and_absent_analysis_evidence_references():
    result = representative_synthesis()
    result.relationships[0].evidence_references = ["EV1"]
    matching_analysis = RepositoryAnalysisResult(
        analysis_id=result.original_analysis_id,
        repository_name=result.repository_name,
        source_type="local",
        source_reference="fixture",
        project_structure=ProjectStructureFinding(summary="Fixture structure."),
        evidence=[evidence()],
        summary="Fixture analysis.",
    )
    present_review = ArchitectureReviewService().review(result, matching_analysis)
    assert any(
        "EV1" in strength.evidence_references
        for strength in present_review.strengths
    )

    result.relationships[0].evidence_references = ["EV_MISSING"]
    absent_review = ArchitectureReviewService().review(result, matching_analysis)
    assert all(
        "EV_MISSING" not in finding.evidence_references
        for finding in absent_review.findings
    )
    assert all(
        "EV_MISSING" not in ref
        for strength in absent_review.strengths
        for ref in strength.evidence_references
    )


def test_review_without_analysis_preserves_synthesis_evidence_and_warns():
    result = representative_synthesis()
    result.relationships.append(ArchitectureRelationship(
        source_component_id="repository_repo",
        target_component_id="project_api",
        relationship_type="imports",
        description="Unresolved dependency.",
        evidence_references=["SYNTHESIS_EV"],
        status=RelationshipStatus.inferred,
        confidence=ConfidenceLevel.medium,
    ))
    review = ArchitectureReviewService().review(result)
    dep001 = [finding for finding in review.findings if finding.rule_id == "DEP-001"]
    assert dep001
    assert all("SYNTHESIS_EV" in finding.evidence_references for finding in dep001)
    assert any(
        "Independent evidence validation was unavailable" in warning
        for warning in review.warnings
    )


def test_integration_data_flow_and_positive_observations():
    result = representative_synthesis()
    result.external_systems = [
        ExternalSystem(
            external_system_id="external_payments",
            name="Payments",
            integration_type="REST API",
            description="Static payment client evidence.",
            evidence_references=["EV1"],
            confidence=ConfidenceLevel.medium,
            status=RelationshipStatus.inferred,
        )
    ]
    review = ArchitectureReviewService().review(result)
    assert any(finding.category.value == "integration_architecture" for finding in review.findings)
    assert review.strengths


def test_data_flow_unknown_endpoints_are_investigation_items():
    result = synthesis(
        components=[],
        data_flows=[ArchitectureDataFlow(
            source_component_id="missing_source",
            target_component_id="missing_target",
            flow_description="Unknown static flow.",
            evidence_references=["EV1"],
            status=RelationshipStatus.inferred,
        )],
    )
    review = ArchitectureReviewService().review(result)
    assert any(finding.rule_id in {"DATA-001", "DATA-002"} for finding in review.findings)
    assert review.overall_review_outcome in {
        ArchitectureReviewOutcome.needs_investigation,
        ArchitectureReviewOutcome.improvements_recommended,
    }


def test_duplicate_findings_are_prevented_and_minimal_synthesis_is_safe():
    result = representative_synthesis()
    result.relationships *= 2
    result.components *= 1
    review = ArchitectureReviewService().review(result)
    ids = [finding.finding_id for finding in review.findings]
    assert len(ids) == len(set(ids))

    minimal = ArchitectureReviewService().review(synthesis())
    assert isinstance(minimal.repository_name, str)
    assert minimal.warnings or minimal.limitations


def test_matching_analysis_is_used_but_different_analysis_is_ignored():
    result = representative_synthesis()
    analysis = RepositoryAnalysisResult(
        analysis_id=result.original_analysis_id,
        repository_name=result.repository_name,
        source_type="local",
        source_reference="fixture",
        project_structure=ProjectStructureFinding(summary="Fixture structure."),
        dependencies=[
            DependencyFinding(source="A", target="B", dependency_type="imports", resolved=False, evidence_references=["EV1"])
        ],
        evidence=[evidence()],
        summary="Fixture analysis.",
    )
    review = ArchitectureReviewService().review(result, analysis)
    assert review.review_metadata["analysis_used"] is True

    other = analysis.model_copy(update={"analysis_id": uuid4()})
    review = ArchitectureReviewService().review(result, other)
    assert review.review_metadata["analysis_used"] is False
    assert any("does not match" in warning for warning in review.warnings)
