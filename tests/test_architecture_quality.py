from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDesign,
    ArchitectureResponse,
    RequirementAnalysis,
)
from app.services.architecture_quality import validate_architecture_quality


def create_quality_test_response(include_result_storage: bool = True) -> ArchitectureResponse:
    components = [
        ArchitectureComponent(
            name="Upload API",
            responsibility=(
                "Authenticate requests and authorize access using tenant identity"
            ),
            technology="Azure Functions",
            rationale="Enforces access controls for each tenant",
        ),
        ArchitectureComponent(
            name="Document Storage",
            responsibility="Store uploaded PDF documents",
            technology="Azure Blob Storage",
            rationale="Stores unstructured files",
        ),
        ArchitectureComponent(
            name="Message Queue",
            responsibility="Queue asynchronous document processing jobs",
            technology="Azure Service Bus",
            rationale="Decouples upload requests from processing",
        ),
        ArchitectureComponent(
            name="Processing Worker",
            responsibility=(
                "Consume queued jobs, process PDFs, and update status"
            ),
            technology="Azure Functions",
            rationale="Supports asynchronous processing",
        ),
        ArchitectureComponent(
            name="Processing Status Store",
            responsibility="Store processing status per tenant and document",
            technology="Azure SQL Database",
            rationale="Supports status queries",
        ),
        ArchitectureComponent(
            name="Results Retrieval API",
            responsibility=(
                "Authorize tenant access and retrieve processed results"
            ),
            technology="Azure Functions",
            rationale="Provides controlled access to results",
        ),
    ]

    if include_result_storage:
        components.append(
            ArchitectureComponent(
                name="Results Storage",
                responsibility="Persist processed output files",
                technology="Azure Blob Storage",
                rationale=(
                    "Stores processing output separately from status metadata"
                ),
            )
        )

    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="openai",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=[
                "Upload PDF files",
                "Process documents asynchronously",
                "Track document status",
                "Return processing results through an API",
            ],
            non_functional_requirements=[
                "Protect tenant data through tenant isolation",
                "Scale to support 10,000 customers",
            ],
            assumptions=[],
            open_questions=[],
        ),
        architecture=ArchitectureDesign(
            summary="Multi-tenant asynchronous PDF processing platform",
            components=components,
            data_flow=[
                "Tenant authenticates and uploads a PDF",
                "Upload API stores the PDF and queues a processing job",
                "Processing Worker consumes the queue and processes the PDF",
                "Worker stores results and updates processing status",
                (
                    "Tenant queries status and retrieves results through an "
                    "authorized API"
                ),
            ],
            mermaid_diagram=(
                "flowchart LR\n"
                'client["Tenant"] --> api["Upload API"]\n'
                'api --> queue["Message Queue"]\n'
                'queue --> worker["Processing Worker"]\n'
                'worker --> status["Processing Status Store"]'
            ),
        ),
        decisions=[],
        risks=[],
        next_steps=["Build a proof of concept"],
    )


def test_complete_architecture_has_no_quality_findings() -> None:
    response = create_quality_test_response()

    findings = validate_architecture_quality(response)

    assert findings == []


def test_missing_result_storage_is_reported() -> None:
    response = create_quality_test_response(include_result_storage=False)

    findings = validate_architecture_quality(response)

    assert any("processed results are persisted" in item for item in findings)


def test_missing_queue_and_worker_are_reported() -> None:
    response = create_quality_test_response()
    response.architecture.components = [
        component
        for component in response.architecture.components
        if component.name not in {"Message Queue", "Processing Worker"}
    ]

    findings = validate_architecture_quality(response)

    assert any("queue and worker" in item for item in findings)


def test_missing_status_component_is_reported() -> None:
    response = create_quality_test_response()
    status_references = {
        "Processing Worker": {
            "responsibility": "Consume queued jobs and process PDFs",
        },
        "Results Storage": {
            "rationale": "Stores processing output separately from metadata",
        },
    }
    response.architecture.components = [
        (
            component.model_copy(update=status_references[component.name])
            if component.name in status_references
            else component
        )
        for component in response.architecture.components
        if component.name != "Processing Status Store"
    ]

    findings = validate_architecture_quality(response)

    assert any("no status component" in item for item in findings)
