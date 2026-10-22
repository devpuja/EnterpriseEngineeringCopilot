
from importlib import import_module
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from main import app
from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDesign,
    ArchitectureResponse,
    RequirementAnalysis,
)


architecture_module = import_module("app.api.architecture")
client = TestClient(app)


def valid_architecture_response() -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="ollama",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=["Upload PDF files"],
            non_functional_requirements=["Tenant isolation"],
            assumptions=[],
            open_questions=[],
        ),
        architecture=ArchitectureDesign(
            summary="Asynchronous PDF processing",
            components=[
                ArchitectureComponent(
                    name="Document Worker",
                    responsibility="Process uploaded PDF files",
                    technology="Azure Functions",
                    rationale="Supports asynchronous processing",
                )
            ],
            data_flow=["Upload PDF", "Process PDF", "Store result"],
            mermaid_diagram=(
                "flowchart LR\n"
                "A[Upload] --> B[Process]\n"
                "B --> C[Store]"
            ),
        ),
        decisions=[],
        risks=[],
        next_steps=["Implement the upload API"],
    )


class FakeArchitectureAgent:
    """Returns a predetermined response without calling an LLM."""

    def __init__(
        self,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.called = False
        self.requirements: str | None = None
        self.model_provider: str | None = None

    async def design(
        self,
        requirements: str,
        model_provider: str,
    ) -> ArchitectureResponse:
        self.called = True
        self.requirements = requirements
        self.model_provider = model_provider

        if self.error is not None:
            raise self.error

        return self.result


@pytest.fixture
def fake_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., FakeArchitectureAgent]:
    def install(
        result: Any = None,
        error: Exception | None = None,
    ) -> FakeArchitectureAgent:
        fake = FakeArchitectureAgent(result=result, error=error)
        monkeypatch.setattr(
            architecture_module,
            "architecture_agent",
            fake,
        )
        return fake

    return install


def test_design_endpoint_returns_200_for_success(
    fake_agent: Callable[..., FakeArchitectureAgent],
) -> None:
    expected = valid_architecture_response()
    fake = fake_agent(result=expected)

    response = client.post(
        "/api/v1/architecture/design",
        json={
            "requirements": (
                "Build a multi-tenant platform for asynchronous PDF processing"
            )
        },
    )

    assert response.status_code == 200
    assert fake.called is True
    assert response.json()["agent"] == "ArchitectureAgent"
    assert response.json()["architecture"]["summary"] == (
        "Asynchronous PDF processing"
    )


def test_design_endpoint_returns_502_for_invalid_model_output(
    fake_agent: Callable[..., FakeArchitectureAgent],
) -> None:
    fake = fake_agent(error=ValueError("The model returned invalid JSON."))

    response = client.post(
        "/api/v1/architecture/design",
        json={
            "requirements": (
                "Build a multi-tenant platform for asynchronous PDF processing"
            )
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The model returned an invalid architecture response."
    )
    assert fake.called is True
    assert "invalid JSON" not in response.text


def test_design_endpoint_returns_502_for_unexpected_failure(
    fake_agent: Callable[..., FakeArchitectureAgent],
) -> None:
    fake = fake_agent(
        error=RuntimeError("Internal provider credentials or details")
    )

    response = client.post(
        "/api/v1/architecture/design",
        json={
            "requirements": (
                "Build a multi-tenant platform for asynchronous PDF processing"
            )
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Architecture generation failed. Check application logs."
    )
    assert "credentials" not in response.text
    assert fake.called is True


def test_design_endpoint_rejects_short_requirements(
    fake_agent: Callable[..., FakeArchitectureAgent],
) -> None:
    fake = fake_agent(result=valid_architecture_response())

    response = client.post(
        "/api/v1/architecture/design",
        json={"requirements": "Too short"},
    )

    assert response.status_code == 422
    assert fake.called is False
