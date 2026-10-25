
import re
from typing import Iterable

from app.api.schemas import (
    ArchitectureResponse,
    ArchitectureReviewFinding,
)


# This parser intentionally supports the simple flowchart syntax generated
# by this project. It is not a complete Mermaid parser.
_NODE_DECLARATION = re.compile(
    r'([A-Za-z][A-Za-z0-9_]*)\s*'
    r'(?:\["([^"]+)"\]|\[([^\]]+)\]|\("([^"]+)"\)|'
    r"\(([^)]*)\)|\{([^}]*)\})"
)

_EXTERNAL_ACTOR_LABELS = {
    "user",
    "client",
    "customer",
    "browser",
    "mobile app",
    "web app",
    "external system",
}


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    text = text.lower()
    return any(term in text for term in terms)


def _normalize_label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _canonical_component_label(value: str) -> str:
    """Normalize common naming variants without hiding real mismatches."""
    normalized = _normalize_label(value)
    aliases = {
        "auth provider": "authentication provider",
        "identity provider": "authentication provider",
        "authentication service": "authentication provider",
    }
    return aliases.get(normalized, normalized)


def _is_api_endpoint_label(value: str) -> bool:
    """API operations are diagram nodes, but need not be standalone components."""
    return bool(
        re.match(
            r"^\s*(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/",
            value,
            flags=re.IGNORECASE,
        )
    )


def _architecture_text(response: ArchitectureResponse) -> str:
    architecture = response.architecture
    parts = [
        architecture.summary,
        architecture.mermaid_diagram,
        *architecture.data_flow,
    ]

    for component in architecture.components:
        parts.extend(
            [
                component.name,
                component.responsibility,
                component.technology,
                component.rationale,
            ]
        )

    for decision in response.decisions:
        parts.extend(
            [
                decision.decision,
                decision.rationale,
                *decision.alternatives,
                *decision.trade_offs,
            ]
        )

    for risk in response.risks:
        parts.extend([risk.risk, risk.impact, risk.mitigation])

    return "\n".join(parts).lower()


def _requirements_text(response: ArchitectureResponse) -> str:
    analysis = response.requirements_analysis
    return "\n".join(
        analysis.functional_requirements
        + analysis.non_functional_requirements
        + analysis.constraints
    ).lower()


def _tenant_implementation_text(response: ArchitectureResponse) -> str:
    """Return implemented design details, excluding aspirational risk mitigations."""
    architecture = response.architecture
    parts = [architecture.summary, architecture.mermaid_diagram, *architecture.data_flow]

    for component in architecture.components:
        parts.extend(
            [component.name, component.responsibility, component.technology, component.rationale]
        )

    for decision in response.decisions:
        parts.extend([decision.decision, decision.rationale, *decision.alternatives, *decision.trade_offs])

    return "\n".join(parts).lower()


def _diagram_labels(diagram: str) -> set[str]:
    """Extract labels from supported Mermaid node declarations."""
    labels: set[str] = set()

    for line in diagram.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("%%"):
            continue

        for match in _NODE_DECLARATION.finditer(stripped):
            label = next(
                (group for group in match.groups()[1:] if group is not None),
                None,
            )
            if label:
                labels.add(label.strip())

    return labels


def _component_diagram_findings(
    response: ArchitectureResponse,
) -> list[ArchitectureReviewFinding]:
    component_names = {
        _canonical_component_label(component.name)
        for component in response.architecture.components
    }

    findings: list[ArchitectureReviewFinding] = []

    for label in sorted(_diagram_labels(response.architecture.mermaid_diagram)):
        normalized = _canonical_component_label(label)

        if (
            not normalized
            or _normalize_label(label) in _EXTERNAL_ACTOR_LABELS
            or _is_api_endpoint_label(label)
        ):
            continue

        if normalized not in component_names:
            findings.append(
                ArchitectureReviewFinding(
                    severity="medium",
                    category="consistency",
                    finding=(
                        f"Diagram node '{label}' has no matching architecture component."
                    ),
                    evidence=(
                        f"The Mermaid diagram declares '{label}', but no "
                        "component has the same normalized name."
                    ),
                    recommendation=(
                        "Add the missing component with its responsibility, "
                        "technology, and rationale, or rename the diagram "
                        "node to match the intended component."
                    ),
                )
            )

    return findings


def _tenant_isolation_findings(
    requirements: str,
    architecture_text: str,
) -> list[ArchitectureReviewFinding]:
    tenant_required = _contains_any(
        requirements,
        (
            "multi-tenant",
            "multi tenant",
            "multi-tenancy",
            "tenant isolation",
            "isolate tenants",
            "tenant data",
            "tenant-specific",
        ),
    )

    if not tenant_required:
        return []

    # Treat identity-derived tenant context and storage enforcement as separate
    # controls. Mentioning either one alone does not prove end-to-end isolation.
    has_identity_bound_authorization = _contains_any(
        architecture_text,
        (
            "tenant-scoped authorization",
            "tenant scoped authorization",
            "tenant-aware authorization",
            "tenant-aware access control",
            "tenant-scoped access",
            "tenant scoped access",
            "tenant context from authenticated identity",
            "tenant context from authenticated principal",
            "derive tenant from authenticated identity",
            "derive tenant from authenticated principal",
            "tenant authorization on every request",
            "enforce tenant authorization on every request",
            "verifies access to the requested job",
            "verify access to the requested job",
            "authorize each operation against that tenant",
            "tenant identity only from validated identity claims",
        ),
    )

    has_storage_boundary_enforcement = _contains_any(
        architecture_text,
        (
            "tenant-scoped storage",
            "tenant scoped storage",
            "tenant-scoped retrieval",
            "tenant scoped retrieval",
            "tenant partition key",
            "tenant-specific partition key",
            "tenant_id validation",
            "tenant id validation",
            "tenant-scoped cosmos db queries",
            "tenant-scoped cosmos db query",
            "tenant partitioning",
            "partitioned by tenant",
            "tenant-specific authorization for blob storage",
            "tenant-specific blob storage access",
            "tenant-scoped blob storage",
            "tenant-specific containers",
            "tenant-specific container",
            "tenant boundaries in storage",
            "enforce tenant boundaries in storage",
            "storage access scoped to the tenant",
        ),
    )

    if has_identity_bound_authorization and has_storage_boundary_enforcement:
        return []

    if has_identity_bound_authorization:
        evidence = (
            "The design describes tenant context derived from authenticated identity "
            "and/or authorization of the requested job, but does not explicitly "
            "demonstrate tenant-scoped enforcement at the underlying data stores."
        )
        recommendation = (
            "Retain the identity-derived tenant context and per-job authorization. "
            "Also specify tenant-scoped Cosmos DB partition/query enforcement and "
            "tenant-authorized Blob Storage access (for example, through an "
            "authorized result reference or narrowly scoped access). Add cross-tenant "
            "tests for status and result retrieval."
        )
        finding_title = "Tenant-scoped storage enforcement is not fully demonstrated."
    else:
        evidence = (
            "The requirements call for multi-tenancy or tenant data protection, "
            "but the design does not clearly establish tenant identity from a "
            "validated principal and authorize each relevant operation."
        )
        recommendation = (
            "Derive tenant identity only from validated identity claims, authorize "
            "every job/status/result operation against that tenant, and enforce "
            "tenant boundaries in storage and retrieval. Add cross-tenant isolation tests."
        )
        finding_title = "Explicit tenant-scoped authorization is not demonstrated."

    return [
        ArchitectureReviewFinding(
            severity="high",
            category="security",
            finding=finding_title,
            evidence=evidence,
            recommendation=recommendation,
        )
    ]


def _authentication_findings(
    response: ArchitectureResponse,
    architecture_text: str,
) -> list[ArchitectureReviewFinding]:
    requirements = _requirements_text(response)
    result_auth_required = _contains_any(
        requirements,
        (
            "result retrieval must be authenticated",
            "authenticate result retrieval",
            "authenticated access to retrieved results",
            "authenticated result retrieval",
            "authenticate access to retrieved results",
        ),
    )
    if not result_auth_required:
        return []

    # A gateway that merely says it authenticates users is not enough to show
    # which identity protocol/provider is selected and where tokens are checked.
    has_concrete_authentication_design = _contains_any(
        architecture_text,
        (
            "microsoft entra id",
            "oauth 2.0",
            "openid connect",
            "oidc",
            "jwt bearer token",
            "jwt access token",
        ),
    )
    has_token_validation_path = _contains_any(
        architecture_text,
        (
            "validates the token",
            "validates access tokens",
            "validates the caller's token",
            "token validation",
            "validate the bearer token",
            "validates caller identity",
        ),
    )

    if has_concrete_authentication_design and has_token_validation_path:
        return []

    missing = list[str]()
    if not has_concrete_authentication_design:
        missing.append("a selected authentication protocol and identity provider")
    if not has_token_validation_path:
        missing.append("an explicit token-validation path for result retrieval")

    return [
        ArchitectureReviewFinding(
            severity="medium",
            category="security",
            finding="Authentication design for result retrieval is unresolved.",
            evidence=(
                "The requirements require authenticated result retrieval, but the "
                "architecture does not explicitly specify " + " and ".join(missing) + "."
            ),
            recommendation=(
                "Choose and document the authentication protocol and identity provider, "
                "identify where access tokens are validated, and enforce authorization "
                "for every status/result request. For an Azure-hosted system, consider "
                "Microsoft Entra ID with OAuth 2.0/OIDC unless requirements dictate otherwise."
            ),
        )
    ]


def _async_reliability_findings(
    requirements: str,
    architecture_text: str,
) -> list[ArchitectureReviewFinding]:
    async_required = _contains_any(
        requirements,
        (
            "asynchronous",
            "async processing",
            "background processing",
            "process in the background",
            "long-running job",
            "long running job",
        ),
    )

    if not async_required:
        return []

    has_queue = _contains_any(
        architecture_text,
        (
            "queue",
            "service bus",
            "event grid",
            "message broker",
            "messaging",
        ),
    )
    has_worker = _contains_any(
        architecture_text,
        (
            "worker",
            "background service",
            "consumer",
            "job processor",
        ),
    )

    if not has_queue or not has_worker:
        missing: list[str] = []
        if not has_queue:
            missing.append("a queue or messaging mechanism")
        if not has_worker:
            missing.append("a background worker or consumer")

        return [
            ArchitectureReviewFinding(
                severity="medium",
                category="reliability",
                finding="The asynchronous processing design is incomplete.",
                evidence=(
                    "The requirements call for asynchronous processing, "
                    "but the design does not clearly identify "
                    + " and ".join(missing)
                    + "."
                ),
                recommendation=(
                    "Define the messaging mechanism and worker/consumer "
                    "responsibilities before implementation."
                ),
            )
        ]

    findings: list[ArchitectureReviewFinding] = []

    # Retry capability and a sufficiently specified retry policy are different.
    has_retry_capability = _contains_any(
        architecture_text,
        ("retry", "retries", "retrying", "retry policy", "retry policies"),
    )
    has_numeric_retry_limit = bool(
        re.search(
            r"\b(?:max(?:imum)?(?:\s+of)?\s+)?\d+\s+(?:retry\s+)?(?:attempts?|retries)\b",
            architecture_text,
        )
    )
    has_backoff_strategy = _contains_any(
        architecture_text,
        (
            "exponential backoff",
            "fixed backoff",
            "constant backoff",
            "linear backoff",
            "jittered backoff",
            "retry delay",
            "retry delays",
        ),
    )
    has_non_retryable_policy = _contains_any(
        architecture_text,
        (
            "non-retryable failures",
            "non-retryable errors",
            "non retryable failures",
            "non retryable errors",
            "do not retry",
            "not retried",
            "permanent failures bypass retries",
        ),
    )

    if not has_retry_capability:
        missing_retry_details = ["retry behavior"]
    else:
        missing_retry_details = list[str]()
        if not has_numeric_retry_limit:
            missing_retry_details.append("a concrete maximum attempt count")
        if not has_backoff_strategy:
            missing_retry_details.append("a named backoff strategy")
        if not has_non_retryable_policy:
            missing_retry_details.append("classification of non-retryable failures")

    if missing_retry_details:
        title = (
            "Explicit retry handling is not described."
            if not has_retry_capability
            else "Retry policy details are underspecified."
        )
        findings.append(
            ArchitectureReviewFinding(
                severity="medium",
                category="reliability",
                finding=title,
                evidence=(
                    "The architecture does not specify "
                    + ", ".join(missing_retry_details)
                    + "."
                ),
                recommendation=(
                    "Define a numeric maximum delivery/processing attempt count, "
                    "a named backoff strategy, retryable versus non-retryable error "
                    "classes, and behavior after attempts are exhausted."
                ),
            )
        )

    reliability_controls: list[tuple[str, tuple[str, ...], str]] = [
        (
            "idempotency",
            ("idempotent", "idempotency", "idempotency key"),
            "Make message processing idempotent so redelivery does not "
            "duplicate side effects.",
        ),
        (
            "dead-letter handling",
            ("dead-letter", "dead letter", "dead-letter queue", "dead letter queue"),
            "Define dead-letter handling, alerting, inspection, and "
            "safe replay procedures.",
        ),
    ]

    for control_name, phrases, recommendation in reliability_controls:
        if not _contains_any(architecture_text, phrases):
            findings.append(
                ArchitectureReviewFinding(
                    severity="medium",
                    category="reliability",
                    finding=(f"Explicit {control_name} handling is not described."),
                    evidence=(
                        "The requirements call for asynchronous processing, "
                        "but the architecture does not explicitly describe "
                        f"{control_name} behavior."
                    ),
                    recommendation=recommendation,
                )
            )

    status_required = _contains_any(
        requirements,
        (
            "status tracking",
            "track processing status",
            "check job status",
            "job status",
            "processing status",
        ),
    )

    if status_required and not _contains_any(
        architecture_text,
        (
            "failed status",
            "failure status",
            "mark the job as failed",
            "mark job as failed",
            "terminal failure state",
            "terminal failed state",
        ),
    ):
        findings.append(
            ArchitectureReviewFinding(
                severity="medium",
                category="reliability",
                finding="Terminal processing failure status is not defined.",
                evidence=(
                    "The requirements include status tracking, but the "
                    "design does not explain how a permanently failed "
                    "processing job is represented."
                ),
                recommendation=(
                    "Define job states, including failed and retrying, "
                    "and ensure callers can retrieve the final state and "
                    "a safe, non-sensitive error description."
                ),
            )
        )

    return findings



def has_explicit_result_persistence(response: ArchitectureResponse) -> bool:
    """Return True only when a result-storage component states its persistence role."""
    result_store_name_terms = (
        "result store",
        "results store",
        "result storage",
        "results storage",
        "result repository",
        "results repository",
    )
    return any(
        _contains_any(component.name.lower(), result_store_name_terms)
        and _describes_result_persistence(f"{component.responsibility} {component.rationale}")
        for component in response.architecture.components
    )


def is_known_api_endpoint_or_component_alias(
    response: ArchitectureResponse, label: str
) -> bool:
    """Identify diagram labels that are endpoints or known component-name aliases."""
    if _is_api_endpoint_label(label):
        return True
    normalized = _canonical_component_label(label)
    return any(
        _canonical_component_label(component.name) == normalized
        for component in response.architecture.components
    )

def _result_retrieval_findings(
    response: ArchitectureResponse,
) -> list[ArchitectureReviewFinding]:
    requirements = _requirements_text(response)
    results_required = _contains_any(
        requirements,
        (
            "return processing results through an api",
            "return results through an api",
            "retrieve results",
            "view results later",
            "download results",
            "results history",
            "processing results",
        ),
    )

    if not results_required:
        return []

    architecture = response.architecture

    has_result_persistence = has_explicit_result_persistence(response)

    retrieval_text = "\\n".join(
        [
            *architecture.data_flow,
            *(
                f"{component.name} {component.responsibility}"
                for component in architecture.components
            ),
        ]
    ).lower()

    # A concrete GET/POST endpoint ending in results is strong evidence.
    has_results_endpoint = bool(
        re.search(r"\b(?:get|post)\s+/[^\s\"']*results?\b", retrieval_text)
    )
    has_retrieval_path = has_results_endpoint or _contains_any(
        retrieval_text,
        (
            "result retrieval endpoint",
            "results endpoint",
            "results api",
            "result retrieval api",
            "retrieve results through the api",
            "retrieve results through api",
            "return results through an api",
            "return processing results through an api",
            "get results from the api",
            "query results through the api",
        ),
    )

    findings: list[ArchitectureReviewFinding] = []

    if not has_result_persistence:
        findings.append(
            ArchitectureReviewFinding(
                severity="medium",
                category="data_flow",
                finding="Persistent storage for processing results is unclear.",
                evidence=(
                    "The requirements call for result retrieval, but the design "
                    "does not declare a result-storage component with an explicit "
                    "persistence responsibility."
                ),
                recommendation=(
                    "Declare a result store, specify its technology and persistence "
                    "responsibility, and document retention and tenant access controls. "
                    "Keep large result payloads separate from job metadata when appropriate."
                ),
            )
        )

    if not has_retrieval_path:
        findings.append(
            ArchitectureReviewFinding(
                severity="medium",
                category="data_flow",
                finding="An API path for retrieving processing results is unclear.",
                evidence=(
                    "The requirements call for results through an API, but the design "
                    "does not clearly identify a result-retrieval endpoint or API path."
                ),
                recommendation=(
                    "Define the result retrieval endpoint, job/result identifier, "
                    "tenant authorization checks, and response behavior while processing "
                    "is incomplete or failed."
                ),
            )
        )

    return findings


def run_deterministic_architecture_checks(response: ArchitectureResponse) -> list[ArchitectureReviewFinding]:
    requirements = _requirements_text(response)
    architecture_text = _architecture_text(response)

    findings: list[ArchitectureReviewFinding] = []

    findings.extend(_component_diagram_findings(response))
    findings.extend(
        _tenant_isolation_findings(
            requirements,
            _tenant_implementation_text(response),
        )
    )
    findings.extend(_authentication_findings(response, architecture_text))
    findings.extend(_async_reliability_findings(requirements, architecture_text))
    findings.extend(_result_retrieval_findings(response))

    return findings


def _describes_result_persistence(text: str) -> bool:
    normalized = " ".join(text.lower().split())

    return bool(
        re.search(
            r"\b(?:persist(?:s|ed|ently)?|store(?:s|d)?|"
            r"save(?:s|d)?|write(?:s|n)?|hold(?:s|ing)?|keep(?:s|ing)?)\b"
            r"[^.!?]{0,120}\bresults?\b",
            normalized,
        )
    )

def has_explicit_result_authentication(
    response: ArchitectureResponse,
) -> bool:
    architecture_text = _architecture_text(response)

    has_provider = _contains_any(
        architecture_text,
        (
            "microsoft entra id",
            "oauth 2.0",
            "openid connect",
            "oidc",
            "jwt bearer token",
            "jwt access token",
        ),
    )

    has_token_validation = _contains_any(
        architecture_text,
        (
            "validates the token",
            "validates access tokens",
            "validates the caller's token",
            "validates the caller's identity and token",
            "token validation",
            "validate the bearer token",
            "validates caller identity",
        ),
    )

    return has_provider and has_token_validation