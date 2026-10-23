
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
        _normalize_label(component.name)
        for component in response.architecture.components
    }

    findings: list[ArchitectureReviewFinding] = []

    for label in sorted(_diagram_labels(response.architecture.mermaid_diagram)):
        normalized = _normalize_label(label)

        if not normalized or normalized in _EXTERNAL_ACTOR_LABELS:
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

    # Look for explicit enforcement mechanisms. Generic references to
    # encryption or security controls alone are not sufficient.
    explicit_tenant_controls = (
        "tenant-scoped authorization",
        "tenant scoped authorization",
        "tenant-aware authorization",
        "tenant-aware access control",
        "tenant-scoped access",
        "tenant scoped access",
        "tenant-scoped storage",
        "tenant scoped storage",
        "tenant-scoped retrieval",
        "tenant scoped retrieval",
        "tenant partition key",
        "tenant-specific partition key",
        "tenant_id validation",
        "tenant id validation",
        "tenant context from authenticated identity",
        "tenant context from authenticated principal",
        "derive tenant from authenticated identity",
        "derive tenant from authenticated principal",
        "authorize the tenant on every request",
        "enforce tenant authorization on every request",
    )

    if _contains_any(architecture_text, explicit_tenant_controls):
        return []

    return [
        ArchitectureReviewFinding(
            severity="high",
            category="security",
            finding=(
                "Explicit tenant-scoped authorization and data isolation "
                "are not demonstrated."
            ),
            evidence=(
                "The requirements call for multi-tenancy or tenant data "
                "protection, but the design does not identify a concrete "
                "tenant enforcement mechanism."
            ),
            recommendation=(
                "Derive tenant context from the authenticated identity, "
                "authorize each operation against that tenant, and enforce "
                "tenant boundaries in storage and retrieval. Add tests that "
                "prove one tenant cannot access another tenant's data."
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

    reliability_controls: list[tuple[str, tuple[str, ...], str]] = [
        (
            "retry",
            ("retry policy", "retry policies", "retry with backoff",
             "exponential backoff"),
            "Define bounded retries with backoff and a policy for "
            "non-retryable failures.",
        ),
        (
            "idempotency",
            ("idempotent", "idempotency", "idempotency key"),
            "Make message processing idempotent so redelivery does not "
            "duplicate side effects.",
        ),
        (
            "dead-letter handling",
            ("dead-letter", "dead letter", "dead-letter queue",
             "dead letter queue"),
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
                    finding=(
                        f"Explicit {control_name} handling is not described."
                    ),
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

    # Examine explicit component responsibilities and data-flow statements.
    # A database used only for job status does not count as result storage.
    result_storage_text = "\n".join(
        f"{component.name} {component.responsibility} {component.rationale}"
        for component in architecture.components
    ).lower()

    result_storage_text += "\n" + "\n".join(
        architecture.data_flow
    ).lower()

    has_result_persistence = (
        _contains_any(
            result_storage_text,
            (
                "persist results",
                "persisted results",
                "result storage",
                "results storage",
                "result repository",
                "results repository",
                "store processing results",
                "stores processing results",
                "store results",
                "stores results",
                "save results",
                "saves results",
                "persist the result",
                "stores the result",
            ),
        )
    )

    # Require a described API/result path. A generic API Gateway by itself
    # does not prove that a result retrieval endpoint exists.
    retrieval_text = "\n".join(
        [
            *architecture.data_flow,
            *(
                f"{component.name} {component.responsibility}"
                for component in architecture.components
            ),
        ]
    ).lower()

    has_retrieval_path = _contains_any(
        retrieval_text,
        (
            "retrieve results",
            "return results",
            "results api",
            "results endpoint",
            "get results",
            "query results",
            "provides results",
            "provides processing results",
            "results through the api",
            "results through an api",
            "results through api",
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
                    "The requirements call for result retrieval, but the "
                    "design does not clearly identify where processing "
                    "results are stored."
                ),
                recommendation=(
                    "Specify the result store, result schema, retention "
                    "policy, and ownership/access controls. Keep large "
                    "result payloads separate from job metadata when "
                    "appropriate."
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
                    "The requirements call for results through an API, "
                    "but the design does not clearly describe how a caller "
                    "requests a result."
                ),
                recommendation=(
                    "Define the result retrieval endpoint, job/result "
                    "identifier, authorization checks, and response "
                    "behavior while processing is incomplete or failed."
                ),
            )
        )

    return findings


def run_deterministic_architecture_checks(
    response: ArchitectureResponse,
) -> list[ArchitectureReviewFinding]:
    requirements = _requirements_text(response)
    architecture_text = _architecture_text(response)

    findings: list[ArchitectureReviewFinding] = []

    findings.extend(_component_diagram_findings(response))
    findings.extend(
        _tenant_isolation_findings(requirements, architecture_text)
    )
    findings.extend(
        _async_reliability_findings(requirements, architecture_text)
    )
    findings.extend(
        _result_retrieval_findings(response)
    )

    return findings