
import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.architecture_agent import ArchitectureAgent
from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDesign,
    ArchitectureResponse,
    RequirementAnalysis,
)


class FakeAgent:
    """Simulates the MAF Agent without calling a real model."""

    def __init__(self, value: Any, text: str = "") -> None:
        self.value = value
        self.text = text
        self.prompt = ""
        self.options: dict[str, Any] | None = None

    async def run(
        self,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> SimpleNamespace:
        self.prompt = prompt
        self.options = options
        return SimpleNamespace(
            value=self.value,
            text=self.text,
        )


def create_valid_response() -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="ollama",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=["Upload PDFs"],
            non_functional_requirements=["Tenant isolation"],
            assumptions=[],
            open_questions=[],
        ),
        architecture=ArchitectureDesign(
            summary="Asynchronous PDF processing",
            components=[
                ArchitectureComponent(
                    name="Document Worker",
                    responsibility="Process uploaded PDFs",
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


def create_test_agent(
    value: Any,
    text: str = "",
) -> tuple[ArchitectureAgent, FakeAgent]:
    # Bypass __init__ so no real model client is created.
    agent = ArchitectureAgent.__new__(ArchitectureAgent)
    fake_agent = FakeAgent(value, text)
    object.__setattr__(agent, "_agent", fake_agent)
    return agent, fake_agent


def test_design_accepts_structured_model_response() -> None:
    async def scenario() -> None:
        model_response = create_valid_response()
        agent, fake_agent = create_test_agent(value=model_response)

        result = await agent.design(
            requirements="Build a multi-tenant PDF processing platform",
            model_provider="ollama",
        )

        assert isinstance(result, ArchitectureResponse)
        assert result.agent == "ArchitectureAgent"
        assert result.model_provider == "ollama"
        assert result.architecture.components[0].name == "Document Worker"
        assert "Build a multi-tenant PDF processing platform" in fake_agent.prompt
        assert fake_agent.options == {
            "response_format": ArchitectureResponse,
        }

    asyncio.run(scenario())


def test_design_accepts_json_dictionary() -> None:
    async def scenario() -> None:
        payload = create_valid_response().model_dump()
        agent, _ = create_test_agent(value=payload)

        result = await agent.design(
            requirements="Build a multi-tenant PDF processing platform",
            model_provider="openai",
        )

        assert isinstance(result, ArchitectureResponse)
        assert result.model_provider == "openai"

    asyncio.run(scenario())


def test_design_accepts_json_text_response() -> None:
    async def scenario() -> None:
        agent, _ = create_test_agent(
            value=None,
            text=create_valid_response().model_dump_json(),
        )

        result = await agent.design(
            requirements="Build a multi-tenant PDF processing platform",
            model_provider="ollama",
        )

        assert isinstance(result, ArchitectureResponse)
        assert result.architecture.summary == "Asynchronous PDF processing"

    asyncio.run(scenario())


def test_design_rejects_invalid_json() -> None:
    async def scenario() -> None:
        agent, _ = create_test_agent(
            value=None,
            text='{"architecture": invalid json}',
        )

        with pytest.raises(ValueError, match="valid JSON"):
            await agent.design(
                requirements="Build a multi-tenant PDF processing platform",
                model_provider="ollama",
            )

    asyncio.run(scenario())


def test_design_rejects_invalid_schema() -> None:
    async def scenario() -> None:
        agent, _ = create_test_agent(
            value={"summary": "Required fields are missing"},
        )

        with pytest.raises(ValueError, match="schema"):
            await agent.design(
                requirements="Build a multi-tenant PDF processing platform",
                model_provider="ollama",
            )

    asyncio.run(scenario())
