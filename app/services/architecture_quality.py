
from app.api.schemas import ArchitectureResponse
from typing import Any, cast


def validate_architecture_quality(response: ArchitectureResponse) -> list[str]:
    """
    Return actionable architecture-quality findings.

    These are heuristic checks, not a substitute for architecture review.
    An empty list means the implemented checks found no issues.
    """
    findings: list[str] = []

    analysis = cast(Any, response).requirements_analysis
    architecture = response.architecture

    requirements_text = " ".join(
        analysis.functional_requirements
        + analysis.non_functional_requirements
    ).lower()

    summary = architecture.summary.lower()
    data_flow = " ".join(architecture.data_flow).lower()

    component_texts = [
        " ".join(
            [
                component.name,
                component.responsibility,
                component.technology,
                component.rationale,
            ]
        ).lower()
        for component in architecture.components
    ]

    all_component_text = " ".join(component_texts)
    all_design_text = " ".join(
        [
            summary,
            data_flow,
            all_component_text,
            " ".join(
                decision.decision + " " + decision.rationale
                for decision in response.decisions
            ).lower(),
            " ".join(
                risk.risk + " " + risk.mitigation
                for risk in response.risks
            ).lower(),
        ]
    )

    # Multi-tenant security: look for explicit isolation or access controls.
    if "tenant" in requirements_text or "multi-tenant" in requirements_text:
        security_indicators = (
            "tenant isolation",
            "tenant-specific",
            "tenant identity",
            "tenant ownership",
            "authorization",
            "authorize",
            "access control",
            "authenticated principal",
        )

        if not any(
            indicator in all_design_text
            for indicator in security_indicators
        ):
            findings.append(
                "Tenant requirements are present, but explicit tenant "
                "isolation or authorization controls are not described."
            )

    # Asynchronous processing: queue and worker must be separate components.
    asynchronous_required = any(
        term in requirements_text
        for term in ("asynchronous", "async", "background processing")
    )

    if asynchronous_required:
        queue_indices = [
            index
            for index, text in enumerate(component_texts)
            if any(term in text for term in ("queue", "message broker"))
        ]

        worker_indices = [
            index
            for index, text in enumerate(component_texts)
            if any(term in text for term in ("worker", "processor"))
        ]

        separate_queue_and_worker = any(
            queue_index != worker_index
            for queue_index in queue_indices
            for worker_index in worker_indices
        )

        if not separate_queue_and_worker:
            findings.append(
                "Asynchronous processing is required, but separate queue "
                "and worker responsibilities are not clearly identified."
            )

        if "queue" not in data_flow or not any(
            term in data_flow for term in ("worker", "process", "consume")
        ):
            findings.append(
                "The data flow does not clearly show queued work reaching "
                "a processing worker."
            )

    # Status tracking.
    status_required = "status" in requirements_text

    if status_required:
        has_status_component = any(
            "status" in text for text in component_texts
        )

        if not has_status_component:
            findings.append(
                "Status tracking is required, but no status component "
                "is identified."
            )

        if "status" not in data_flow:
            findings.append(
                "The data flow does not explain how processing status "
                "is updated or retrieved."
            )

    # Result retrieval and persistence.
    results_required = "result" in requirements_text

    if results_required:
        has_results_api = any(
            "result" in text
            and any(term in text for term in ("api", "retriev", "download"))
            for text in component_texts
        )

        if not has_results_api:
            findings.append(
                "Results are required, but a results retrieval API or "
                "equivalent responsibility is not identified."
            )

        has_persistent_results = any(
            any(term in text for term in ("result", "output"))
            and any(term in text for term in ("store", "persist", "save"))
            for text in component_texts
        )

        if not has_persistent_results:
            findings.append(
                "The architecture does not explicitly identify where "
                "processed results are persisted."
            )

    return findings