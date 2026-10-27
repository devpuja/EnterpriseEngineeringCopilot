from app.api.schemas import RequirementAnalysis
from app.services.azure_pdf_reference_architecture import (
    build_azure_pdf_reference_architecture,
    matches_azure_pdf_platform,
)
from app.services.architecture_review_checks import (
    run_deterministic_architecture_checks,
)
from app.services.diagram_validator import validate_mermaid_flowchart


PLATFORM_REQUIREMENTS = (
    "Design a multi-tenant Azure PDF platform with asynchronous processing "
    "and authenticated result retrieval for at least 10,000 customers."
)


def test_reference_architecture_matches_only_azure_pdf_platform_requests():
    assert matches_azure_pdf_platform(PLATFORM_REQUIREMENTS)
    assert not matches_azure_pdf_platform(
        "Design a multi-tenant Azure case-management system."
    )
    assert not matches_azure_pdf_platform(
        "Design an asynchronous PDF platform on AWS."
    )


def test_reference_architecture_covers_required_platform_controls():
    analysis = RequirementAnalysis(
        functional_requirements=[],
        non_functional_requirements=[],
        assumptions=[],
        open_questions=[],
    )

    response = build_azure_pdf_reference_architecture(
        requirements_analysis=analysis,
        model_provider="OPENAI",
    )

    component_names = {item.name for item in response.architecture.components}
    component_technologies = " ".join(
        item.technology for item in response.architecture.components
    )
    design_text = " ".join(
        response.architecture.data_flow
        + [
            item.responsibility
            for item in response.architecture.components
        ]
        + [
            item.decision + " " + item.rationale
            for item in response.decisions
        ]
    ).lower()

    assert response.model_provider == "openai"
    assert {
        "API Gateway",
        "Application API",
        "Identity Provider",
        "Message Queue",
        "Document Processing Worker",
        "Processing Status Store",
        "Processing Results Store",
        "Monitoring and Alerting",
    }.issubset(component_names)
    assert "Azure API Management" in component_technologies
    assert ".NET REST API" in component_technologies
    assert "Microsoft Entra ID" in component_technologies
    assert "Azure Service Bus" in component_technologies
    assert "Azure Cosmos DB" in component_technologies
    assert "Azure Blob Storage" in component_technologies
    assert "Azure Monitor" in component_technologies
    assert "maximum of 5 attempts total" in design_text
    assert "exponential backoff" in design_text
    assert "dead-letter" in design_text
    assert "tenant-partitioned" in design_text
    assert "get /jobs/{jobid}/results" in design_text
    assert "queued" in design_text
    assert "processing" in design_text
    assert "completed" in design_text
    assert "failed" in design_text
    assert response.review is not None
    assert response.review.approval_recommendation == "approve"
    assert response.review.findings == []
    assert run_deterministic_architecture_checks(response) == []
    assert validate_mermaid_flowchart(
        response.architecture.mermaid_diagram
    ) == []


def test_reference_analysis_does_not_add_compliance_or_capacity_targets():
    response = build_azure_pdf_reference_architecture(
        requirements_analysis=RequirementAnalysis(
            functional_requirements=[],
            non_functional_requirements=[],
            assumptions=[],
            open_questions=[
                "What security measures will be used for authentication and authorization?",
                "What service-level objective is required for processing?",
            ],
        ),
        model_provider="openai",
    )

    analysis_text = " ".join(
        response.requirements_analysis.non_functional_requirements
        + response.requirements_analysis.constraints
    ).lower()

    assert "at least 10,000 customers" in analysis_text
    assert "throughput target" in analysis_text
    assert "hipaa" not in analysis_text
    assert "99.99%" not in analysis_text
    assert response.requirements_analysis.open_questions == [
        "What service-level objective is required for processing?",
        "What PDF size, upload rate, and processing-time objectives should load tests use?",
        "What output format and result-retention period are required?",
        "How are customer organizations onboarded and mapped to Microsoft Entra ID claims?",
        "Are data-residency or regulatory obligations applicable?",
    ]
