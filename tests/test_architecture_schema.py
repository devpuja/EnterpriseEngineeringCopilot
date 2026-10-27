
import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDesign,
    ArchitectureRequest,
    ArchitectureResponse,
    RequirementAnalysis,
)


def test_architecture_request_rejects_short_requirements():
    with pytest.raises(ValidationError):
        ArchitectureRequest(requirements="Too short")


def test_architecture_response_accepts_valid_data():
    response = ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="openai",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=["Upload PDFs"],
            non_functional_requirements=["Tenant isolation"],
            assumptions=[],
            open_questions=[],
        ),
        architecture=ArchitectureDesign(
            summary="Queue-based document processing",
            components=[
                ArchitectureComponent(
                    name="Worker",
                    responsibility="Processes queued documents",
                    technology="Azure Functions",
                    rationale="Supports asynchronous processing",
                )
            ],
            data_flow=["Upload", "Queue", "Process", "Store"],
            mermaid_diagram=(
                "flowchart LR\n"
                "A[Upload] --> B[Queue]\n"
                "B --> C[Worker]"
            ),
        ),
        decisions=[],
        risks=[],
        next_steps=["Implement the upload API"],
    )

    assert response.agent == "ArchitectureAgent"
    assert response.architecture.components[0].name == "Worker"


def test_architecture_response_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        ArchitectureResponse.model_validate(
            {
                "agent": "ArchitectureAgent",
                "model_provider": "openai",
            }
        )
