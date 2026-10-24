
from types import SimpleNamespace

import pytest

from app.agents.architecture_review_agent import ArchitectureReviewAgent
from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDecision,
    ArchitectureDesign,
    ArchitectureRisk,
    ArchitectureResponse,
    ArchitectureReview,
    ArchitectureReviewFinding,
    RequirementAnalysis,
)
from app.services.architecture_review_checks import (
    run_deterministic_architecture_checks,
)
from app.api.schemas import ArchitectureReviewFinding
from app.services.review_finding_merge import merge_review_findings


def make_architecture_response() -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="openai",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=[
                "Users can submit long-running jobs.",
                "Users can check job status.",
                "Users can retrieve results later.",
            ],
            non_functional_requirements=[
                "The system must support multi-tenant isolation.",
            ],
            assumptions=[],
            open_questions=[],
            constraints=[],
        ),
        architecture=ArchitectureDesign(
            summary="A simple API processes user requests.",
            components=[
                ArchitectureComponent(
                    name="API",
                    responsibility="Accepts user requests.",
                    technology="FastAPI",
                    rationale="Provides an HTTP API.",
                ),
            ],
            data_flow=["User sends a request to the API."],
            mermaid_diagram=(
                'flowchart LR\n'
                '    User["User"] --> API["API"]'
            ),
        ),
        decisions=[
            ArchitectureDecision(
                decision="Use an HTTP API.",
                rationale="Provides a standard integration interface.",
                alternatives=["Command-line application"],
                trade_offs=["Requires API hosting."],
            )
        ],
        risks=[],
        next_steps=[],
    )


class FakeReviewAgent:
    def __init__(self, result: object):
        self.result = result
        self.last_prompt = None
        self.last_options: dict[str, object] | None = None

    async def run(self, prompt: str, options: dict[str, object] | None = None):
        self.last_prompt = prompt
        self.last_options = options
        return self.result


def test_deterministic_checks_find_missing_tenant_isolation():
    response = make_architecture_response()

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "security"
        and "tenant-scoped authorization" in finding.finding.lower()
        for finding in findings
    )


def test_deterministic_checks_find_incomplete_async_design():
    response = make_architecture_response()

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "reliability"
        and "asynchronous" in finding.finding.lower()
        for finding in findings
    )


def test_deterministic_checks_find_missing_result_persistence():
    response = make_architecture_response()

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "data_flow"
        and "storage" in finding.finding.lower()
        for finding in findings
    )
    

def test_component_diagram_check_flags_undeclared_component():
    response = make_architecture_response()
    response.architecture.mermaid_diagram = (
        'flowchart LR\n'
        '    User["User"] --> API["API"]\n'
        '    API --> cache["Redis Cache"]'
    )

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "consistency"
        and "Redis Cache" in finding.finding
        for finding in findings
    )


def test_tenant_specific_encryption_alone_is_not_tenant_isolation():
    response = make_architecture_response()
    response.risks.append(
        ArchitectureRisk(
            risk="Cross-tenant data exposure.",
            impact="One tenant may access another tenant's information.",
            mitigation=(
                "Use tenant-specific encryption and encryption at rest."
            ),
        )
    )

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "security"
        and "tenant-scoped authorization" in finding.finding.lower()
        for finding in findings
    )


def test_async_design_flags_missing_failure_controls():
    response = make_architecture_response()

    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Message Queue",
                responsibility="Queues asynchronous jobs.",
                technology="Azure Service Bus",
                rationale="Decouples processing.",
            ),
            ArchitectureComponent(
                name="Processing Worker",
                responsibility="Processes queued documents.",
                technology="Azure Functions",
                rationale="Scales processing independently.",
            ),
        ]
    )
    response.architecture.data_flow = [
        "API sends jobs to Message Queue.",
        "Processing Worker consumes messages.",
    ]

    findings = run_deterministic_architecture_checks(response)

    finding_text = " ".join(f.finding.lower() for f in findings)

    assert "retry" in finding_text
    assert "idempotency" in finding_text
    assert "dead-letter" in finding_text
    assert "failure status" in finding_text


def test_diagram_with_declared_components_has_no_consistency_finding():
    response = make_architecture_response()
    response.architecture.mermaid_diagram = (
        'flowchart LR\n'
        '    User["User"] --> api["API"]'
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "consistency"
        for finding in findings
    )



def test_status_store_alone_does_not_prove_result_persistence():
    response = make_architecture_response()

    response.architecture.components.append(
        ArchitectureComponent(
            name="Processing Status Store",
            responsibility="Tracks document processing status.",
            technology="Azure Cosmos DB",
            rationale="Stores job status for status queries.",
        )
    )
    response.architecture.data_flow = [
        "Worker updates processing status in Processing Status Store."
    ]

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "data_flow"
        and "persistent storage" in finding.finding.lower()
        for finding in findings
    )


def test_explicit_result_store_satisfies_persistence_check():
    response = make_architecture_response()

    response.architecture.components.append(
        ArchitectureComponent(
            name="Processing Results Store",
            responsibility="Persists processing results for later retrieval.",
            technology="Azure Blob Storage",
            rationale="Stores generated document processing results.",
        )
    )
    response.architecture.data_flow = [
        "Worker stores processing results in Processing Results Store.",
        "API provides results to users.",
    ]

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "data_flow"
        and "persistent storage" in finding.finding.lower()
        for finding in findings
    )



def test_explicit_result_retrieval_endpoint_satisfies_retrieval_check():
    response = make_architecture_response()
    response.architecture.components.append(
        ArchitectureComponent(
            name="Processing Results Store",
            responsibility="Persistently stores processed results.",
            technology="Azure Blob Storage",
            rationale="Stores processed results for later retrieval.",
        )
    )
    response.architecture.data_flow = [
        "The client requests GET /jobs/{jobId}/results through API Gateway.",
        "The API validates identity and tenant authorization.",
        "The service reads the result reference from Processing Status Store.",
        "The service fetches the result from Processing Results Store and returns it.",
    ]

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "data_flow"
        and "api path for retrieving" in finding.finding.lower()
        for finding in findings
    )
    assert not any(
        finding.category == "data_flow"
        and "persistent storage" in finding.finding.lower()
        for finding in findings
    )


def test_risk_mitigation_alone_does_not_prove_tenant_isolation():
    response = make_architecture_response()
    response.risks.append(
        ArchitectureRisk(
            risk="Cross-tenant data exposure.",
            impact="A tenant may access another tenant's data.",
            mitigation="Implement tenant-scoped authorization on every request.",
        )
    )

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "security"
        and "tenant-scoped authorization" in finding.finding.lower()
        for finding in findings
    )


def test_bounded_retries_without_limit_and_backoff_are_underspecified():
    response = make_architecture_response()
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Message Queue",
                responsibility="Queues asynchronous jobs with bounded retries.",
                technology="Azure Service Bus",
                rationale="Decouples processing from requests.",
            ),
            ArchitectureComponent(
                name="Processing Worker",
                responsibility="Processes queued jobs.",
                technology="Azure Functions",
                rationale="Runs processing tasks in the background.",
            ),
        ]
    )
    response.architecture.data_flow = [
        "API sends jobs to Message Queue.",
        "Processing Worker consumes messages.",
    ]

    findings = run_deterministic_architecture_checks(response)

    assert any(
        finding.category == "reliability"
        and "retry policy details are underspecified" in finding.finding.lower()
        for finding in findings
    )


def test_retry_limit_and_backoff_are_recognized_as_policy_details():
    response = make_architecture_response()
    response.architecture.components.extend(
        [
            ArchitectureComponent(
                name="Message Queue",
                responsibility="Queues asynchronous jobs with a maximum of 5 attempts and exponential backoff.",
                technology="Azure Service Bus",
                rationale="Defines bounded retries for transient errors.",
            ),
            ArchitectureComponent(
                name="Processing Worker",
                responsibility="Processes queued jobs idempotently.",
                technology="Azure Functions",
                rationale="Runs processing tasks in the background.",
            ),
        ]
    )
    
    response.architecture.data_flow = [
        "The worker retries transient failures up to 5 attempts "
        "using exponential backoff. Non-retryable errors are not retried."
    ]

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "reliability"
        and "retry policy details" in finding.finding.lower()
        for finding in findings
    )


def test_merge_keeps_finding_evidence_and_recommendation_together():
    lower_severity = ArchitectureReviewFinding(
        severity="medium",
        category="security",
        finding="Tenant isolation needs clarification.",
        evidence=(
            "The design discusses tenant-specific encryption, key rotation, "
            "and secure storage but does not establish request-level authorization."
        ),
        recommendation="Document key rotation, encryption scope, and storage controls in detail.",
    )
    higher_severity = ArchitectureReviewFinding(
        severity="high",
        category="security",
        finding="Tenant-scoped authorization is not demonstrated.",
        evidence="The authenticated tenant identity is not enforced during result retrieval.",
        recommendation="Derive tenant context from identity and authorize each result retrieval.",
    )

    merged = merge_review_findings([lower_severity, higher_severity])

    assert len(merged) == 1
    assert merged[0].severity == "high"
    assert merged[0].finding == higher_severity.finding
    assert merged[0].evidence == higher_severity.evidence
    assert merged[0].recommendation == higher_severity.recommendation


def test_semantically_duplicate_tenant_findings_are_merged():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="security",
            finding=(
                "Potential for data leakage between tenants due to "
                "unclear isolation mechanisms."
            ),
            evidence=(
                "The architecture mentions data security but does not "
                "describe tenant isolation."
            ),
            recommendation="Define tenant-specific access controls.",
        ),
        ArchitectureReviewFinding(
            severity="high",
            category="security",
            finding=(
                "Explicit tenant-scoped authorization and data isolation "
                "are not demonstrated."
            ),
            evidence=(
                "Tenant context must be derived from the authenticated "
                "identity and enforced for each relevant operation."
            ),
            recommendation=(
                "Enforce tenant authorization on every operation and "
                "add cross-tenant isolation tests."
            ),
        ),
    ]

    merged = merge_review_findings(findings)

    assert len(merged) == 1
    assert merged[0].severity == "high"
    assert "tenant" in merged[0].finding.lower()
    assert "authenticated" in merged[0].evidence.lower()


def test_distinct_reliability_findings_are_not_merged():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Explicit retry handling is not described.",
            evidence="The architecture does not specify retry behavior.",
            recommendation="Define bounded retries with backoff.",
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



def test_review_finding_merge_removes_repeated_adjacent_words():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Dead-letter handling handling is not described.",
            evidence="The design does not define dead-letter handling handling.",
            recommendation="Define dead-letter handling handling procedures.",
        )
    ]

    merged = merge_review_findings(findings)

    assert len(merged) == 1
    assert "handling handling" not in merged[0].finding.lower()
    assert "handling handling" not in merged[0].evidence.lower()
    assert "handling handling" not in merged[0].recommendation.lower()


def test_auth_provider_alias_matches_authentication_provider():
    response = make_architecture_response()

    response.architecture.components.append(
        ArchitectureComponent(
            name="Authentication Provider",
            responsibility="Authenticates API callers.",
            technology="Microsoft Entra ID",
            rationale="Provides centralized identity management.",
        )
    )
    response.architecture.mermaid_diagram = (
        'flowchart LR\n'
        '    auth["Auth Provider"]'
    )

    findings = run_deterministic_architecture_checks(response)

    assert not any(
        finding.category == "consistency"
        and "Auth Provider" in finding.finding
        for finding in findings
    )


def test_duplicate_retry_policy_findings_are_merged_but_idempotency_is_preserved():
    findings = [
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding=(
                "Unspecified retry limits and backoff strategies "
                "for message processing"
            ),
            evidence=(
                "The design mentions retries but does not specify "
                "limits or backoff."
            ),
            recommendation=(
                "Define retry limits and a backoff strategy."
            ),
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Retry policy details are underspecified.",
            evidence=(
                "The architecture does not specify a maximum "
                "retry-attempt count."
            ),
            recommendation=(
                "Specify maximum attempts and handling for "
                "non-retryable failures."
            ),
        ),
        ArchitectureReviewFinding(
            severity="medium",
            category="reliability",
            finding="Explicit idempotency handling is not described.",
            evidence=(
                "Message redelivery may repeat processing."
            ),
            recommendation=(
                "Make message processing idempotent."
            ),
        ),
    ]

    merged = merge_review_findings(findings)

    assert len(merged) == 2

    retry_findings = [
        finding
        for finding in merged
        if "retry" in finding.finding.lower()
    ]
    idempotency_findings = [
        finding
        for finding in merged
        if "idempotency" in finding.finding.lower()
    ]

    assert len(retry_findings) == 1
    assert len(idempotency_findings) == 1
    assert retry_findings[0].severity == "medium"
    assert retry_findings[0].evidence
    assert retry_findings[0].recommendation

    
    
@pytest.mark.asyncio
async def test_review_merges_findings_and_does_not_approve_high_risk():
    response = make_architecture_response()

    model_review = ArchitectureReview(
        summary="The design needs security and reliability improvements.",
        findings=[
            ArchitectureReviewFinding(
                severity="medium",
                category="maintainability",
                finding="Component responsibilities need clarification.",
                evidence="The API is the only listed component.",
                recommendation="Separate responsibilities where needed.",
            )
        ],
        approval_recommendation="approve",
    )

    fake_agent = FakeReviewAgent(
        SimpleNamespace(value=model_review)
    )
    reviewer = ArchitectureReviewAgent(agent=fake_agent)

    result = await reviewer.review(response)

    assert result.approval_recommendation == "revise"
    assert any(
        finding.category == "security"
        for finding in result.findings
    )
    assert any(
        finding.category == "maintainability"
        for finding in result.findings
    )
    assert fake_agent.last_options == {
        "response_format": ArchitectureReview
    }


@pytest.mark.asyncio
async def test_review_rejects_invalid_json():
    reviewer = ArchitectureReviewAgent(
        agent=FakeReviewAgent(
            SimpleNamespace(value=None, text="{invalid json")
        )
    )

    with pytest.raises(ValueError, match="invalid JSON"):
        await reviewer.review(make_architecture_response())


@pytest.mark.asyncio
async def test_review_rejects_missing_output():
    reviewer = ArchitectureReviewAgent(
        agent=FakeReviewAgent(
            SimpleNamespace(value=None, text=None)
        )
    )

    with pytest.raises(ValueError, match="no structured review"):
        await reviewer.review(make_architecture_response())