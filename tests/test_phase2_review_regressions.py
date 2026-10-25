from types import SimpleNamespace

import pytest

from app.agents.architecture_review_agent import ArchitectureReviewAgent
from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureReview,
    ArchitectureReviewFinding,
    ArchitectureRisk,
)
from app.services.architecture_review_checks import (
    run_deterministic_architecture_checks,
)
from app.services.review_finding_merge import merge_review_findings
from test_architecture_review_agent import FakeReviewAgent, make_architecture_response


def test_http_endpoint_and_auth_provider_alias_do_not_create_component_mismatch():
    response = make_architecture_response()
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Authentication Provider",
                responsibility="Authenticates callers.",
                technology="Microsoft Entra ID",
                rationale="Central identity provider.",
            ),
        ]
    )
    response.architecture.mermaid_diagram = (
        "flowchart LR\n"
        '    api["API"] --> endpoint["GET /jobs/{jobId}/results"]\n'
        '    api --> auth["Auth Provider"]'
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "consistency"
        and (
            "GET /jobs/{jobId}/results" in finding.finding
            or "Auth Provider" in finding.finding
        )
        for finding in findings
    )


@pytest.mark.asyncio
async def test_model_review_drops_only_contradicted_result_and_diagram_findings():
    response = make_architecture_response()
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Processing Results Store",
                responsibility="Persistently stores processed results.",
                technology="Azure Blob Storage",
                rationale="Stores processed results for later retrieval.",
            ),
            ArchitectureComponent(
                name="Authentication Provider",
                responsibility="Authenticates callers.",
                technology="Microsoft Entra ID",
                rationale="Central identity provider.",
            ),
        ]
    )
    response.architecture.data_flow = [
        "The client requests GET /jobs/{jobId}/results through API Gateway.",
        "The service fetches the result from Processing Results Store and returns it.",
    ]
    response.architecture.mermaid_diagram = (
        "flowchart LR\n"
        '    api["API"] --> endpoint["GET /jobs/{jobId}/results"]\n'
        '    api --> auth["Auth Provider"]'
    )
    model_review = ArchitectureReview(
        summary="Review identifies possible gaps.",
        findings=[
            ArchitectureReviewFinding(
                severity="medium",
                category="data_flow",
                finding="Persistent storage for processing results is unclear.",
                evidence="The reviewer did not identify a result store.",
                recommendation="Declare a result store.",
            ),
            ArchitectureReviewFinding(
                severity="medium",
                category="consistency",
                finding=(
                    "Diagram node 'GET /jobs/{jobId}/results' has no matching "
                    "architecture component."
                ),
                evidence="The endpoint is not listed as a component.",
                recommendation="Add an endpoint component.",
            ),
            ArchitectureReviewFinding(
                severity="medium",
                category="consistency",
                finding=(
                    "Diagram node 'Auth Provider' has no matching architecture component."
                ),
                evidence="The label differs from Authentication Provider.",
                recommendation="Add a separate Auth Provider component.",
            ),
            ArchitectureReviewFinding(
                severity="medium",
                category="consistency",
                finding=(
                    "Diagram node 'Tenant / Client' has no matching architecture component."
                ),
                evidence="The external actor is not listed as an internal component.",
                recommendation="Add a Tenant / Client component.",
            ),
            ArchitectureReviewFinding(
                severity="medium",
                category="reliability",
                finding="Explicit idempotency handling is not described.",
                evidence="Message redelivery may repeat processing.",
                recommendation="Make message processing idempotent.",
            ),
        ],
        approval_recommendation="revise",
    )
    reviewer = ArchitectureReviewAgent(
        agent=FakeReviewAgent(SimpleNamespace(value=model_review))
    )

    result = await reviewer.review(response)
    titles = [finding.finding.lower() for finding in result.findings]

    assert not any("persistent storage for processing results is unclear" in title for title in titles)
    assert not any("get /jobs/{jobid}/results" in title for title in titles)
    assert not any("auth provider" in title and "matching architecture component" in title for title in titles)
    assert not any("tenant / client" in title and "matching architecture component" in title for title in titles)
    assert any("idempotency" in title for title in titles)


def test_retry_policy_findings_merge_without_merging_idempotency():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Lack of clarity on retry limits and backoff strategies for message processing.",
            evidence="Retry limits and backoff are not specified.",
            recommendation="Define retry limits and backoff.",
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Retry policy details are underspecified.",
            evidence="The maximum retry-attempt count is not stated.",
            recommendation="Specify maximum attempts and non-retryable failures.",
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Explicit idempotency handling is not described.",
            evidence="Message redelivery may repeat processing.",
            recommendation="Make message processing idempotent.",
        ),
    ]

    merged = merge_review_findings(findings)
    assert len(merged) == 2
    assert sum("retry" in finding.finding.lower() for finding in merged) == 1
    assert sum("idempotency" in finding.finding.lower() for finding in merged) == 1


def test_tenant_context_without_storage_enforcement_remains_a_high_finding():
    response = make_architecture_response()
    response.requirements_analysis.functional_requirements.append(
        "The system must ensure tenant data isolation."
    )
    response.architecture.data_flow = [
        "The service derives tenant context from authenticated identity and verifies access to the requested job."
    ]

    findings = run_deterministic_architecture_checks(response)
    tenant_findings = [
        finding for finding in findings
        if finding.category == "security" and "tenant" in finding.finding.lower()
    ]

    assert len(tenant_findings) == 1
    assert "storage enforcement" in tenant_findings[0].finding.lower()
    assert "does not explicitly demonstrate tenant-scoped enforcement" in tenant_findings[0].evidence.lower()


def test_tenant_identity_and_storage_controls_satisfy_isolation_check():
    response = make_architecture_response()
    response.requirements_analysis.functional_requirements.append(
        "The system must ensure tenant data isolation."
    )
    response.architecture.data_flow = [
        "The service derives tenant context from authenticated identity and authorizes every request.",
        "Cosmos DB queries use a tenant partition key and Blob Storage access is tenant-scoped.",
    ]

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "security" and "tenant" in finding.finding.lower()
        for finding in findings
    )


def test_authenticated_result_retrieval_requires_concrete_auth_design():
    response = make_architecture_response()
    response.requirements_analysis.non_functional_requirements.append(
        "Result retrieval must be authenticated."
    )
    response.requirements_analysis.open_questions.append(
        "How will authentication be managed for the API (e.g., OAuth or API keys)?"
    )
    response.architecture.components.append(
        ArchitectureComponent(
            name="API Gateway",
            responsibility="Handles incoming requests and authenticates users.",
            technology="Azure API Management",
            rationale="Provides a managed API entry point.",
        )
    )

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "security"
        and "authentication design for result retrieval is unresolved" in finding.finding.lower()
        for finding in findings
    )


def test_concrete_auth_provider_and_token_validation_satisfy_auth_check():
    response = make_architecture_response()
    response.requirements_analysis.non_functional_requirements.append(
        "Result retrieval must be authenticated."
    )
    response.architecture.components.append(
        ArchitectureComponent(
            name="Authentication Provider",
            responsibility="Validates access tokens for result retrieval.",
            technology="Microsoft Entra ID with OAuth 2.0/OIDC access tokens",
            rationale="Provides centralized identity and access management.",
        )
    )
    response.architecture.data_flow.append(
        "API Gateway validates the caller's token before every result request."
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "security"
        and "authentication design for result retrieval is unresolved" in finding.finding.lower()
        for finding in findings
    )


def test_retry_policy_requires_limit_backoff_and_non_retryable_classification():
    response = make_architecture_response()
    response.requirements_analysis.functional_requirements.append(
        "The system must process jobs asynchronously with bounded retries."
    )
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Message Queue",
                responsibility="Queues asynchronous jobs and retries failed messages.",
                technology="Azure Service Bus",
                rationale="Supports message delivery and retry behavior.",
            ),
            ArchitectureComponent(
                name="Processing Worker",
                responsibility="Processes queued jobs idempotently.",
                technology="Azure Functions",
                rationale="Processes jobs in the background.",
            ),
        ]
    )
    response.architecture.data_flow = [
        "The worker retries transient failures using bounded retries."
    ]

    findings = run_deterministic_architecture_checks(response)
    retry_finding = next(
        finding for finding in findings
        if finding.category == "reliability" and "retry policy details" in finding.finding.lower()
    )

    assert "maximum attempt count" in retry_finding.evidence.lower()
    assert "backoff strategy" in retry_finding.evidence.lower()
    assert "non-retryable" in retry_finding.evidence.lower()


def test_tenant_client_is_treated_as_external_actor_not_component():
    response = make_architecture_response()
    response.architecture.mermaid_diagram = (
        'flowchart LR\\n'
        '    client["Tenant / Client"] --> api["API"]'
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "consistency"
        and "tenant / client" in finding.finding.lower()
        for finding in findings
    )


def test_retry_logic_and_retry_policy_findings_merge_but_keep_idempotency_separate():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Lack of clarity on retry logic and error handling for processing failures.",
            evidence="Retry classification and backoff are not specified.",
            recommendation="Define retry policy and failure classification.",
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Retry policy details are underspecified.",
            evidence="Maximum attempts are not stated.",
            recommendation="Specify maximum attempts and backoff.",
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Explicit idempotency handling is not described.",
            evidence="Message redelivery may repeat side effects.",
            recommendation="Make processing idempotent.",
        ),
    ]

    merged = merge_review_findings(findings)

    assert len(merged) == 2
    assert sum("retry" in item.finding.lower() for item in merged) == 1
    assert sum("idempotency" in item.finding.lower() for item in merged) == 1


def test_async_capacity_check_does_not_accept_risk_mitigation_as_design_evidence():
    response = make_architecture_response()
    response.requirements_analysis.non_functional_requirements.extend(
        [
            "The platform must support at least 10,000 customers.",
            "Performance must accommodate concurrent uploads and processing requests.",
        ]
    )
    response.requirements_analysis.functional_requirements.append(
        "Documents must be processed asynchronously."
    )
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Message Queue",
                responsibility="Buffers asynchronous processing messages.",
                technology="Azure Service Bus",
                rationale="Decouples uploads from processing.",
            ),
            ArchitectureComponent(
                name="Document Worker",
                responsibility="Processes queued documents.",
                technology="Azure Functions",
                rationale="Supports background processing.",
            ),
        ]
    )
    response.risks.append(
        ArchitectureRisk(
            risk="Queue overload during traffic spikes.",
            impact="Processing delays.",
            mitigation="Monitor queue depth and autoscale workers with backpressure.",
        )
    )

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "scalability"
        and "queue backlog" in finding.finding.lower()
        for finding in findings
    )


def test_async_capacity_check_accepts_explicit_queue_and_worker_controls():
    response = make_architecture_response()
    response.requirements_analysis.non_functional_requirements.extend(
        [
            "The platform must support at least 10,000 customers.",
            "Performance must accommodate concurrent uploads and processing requests.",
        ]
    )
    response.requirements_analysis.functional_requirements.append(
        "Documents must be processed asynchronously."
    )
    response.architecture.data_flow.extend(
        [
            "Monitor Azure Service Bus queue depth and oldest message age.",
            "Scale worker instances horizontally based on queue depth.",
            "Apply bounded concurrency and backpressure to protect downstream storage.",
        ]
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "scalability"
        and "queue backlog" in finding.finding.lower()
        for finding in findings
    )
