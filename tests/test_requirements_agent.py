
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.requirements_agent import RequirementsAnalysisAgent
from app.api.schemas import RequirementAnalysis


def valid_analysis() -> RequirementAnalysis:
    return RequirementAnalysis(
        functional_requirements=[
            "Users can upload PDF documents.",
            "Users can retrieve processing results.",
        ],
        non_functional_requirements=[
            "The system must isolate tenant data."
        ],
        assumptions=["Users are authenticated."],
        open_questions=["What is the expected maximum file size?"],
        constraints=["The system must use Microsoft Azure."],
    )


class FakeAgent:
    def __init__(self, value: Any = None, text: str | None = None) -> None:
        self.value = value
        self.text = text
        self.received_prompt: str | None = None
        self.received_options: dict[str, Any] | None = None

    async def run(
        self,
        prompt: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> SimpleNamespace:
        self.received_prompt = prompt
        self.received_options = options or {}

        return SimpleNamespace(value=self.value, text=self.text)


@pytest.mark.asyncio
async def test_analyze_returns_structured_model() -> None:
    expected = valid_analysis()
    fake_agent = FakeAgent(value=expected)
    agent = RequirementsAnalysisAgent(agent=fake_agent)

    result = await agent.analyze(
        "Build an Azure application that accepts PDFs and returns results."
    )

    assert result == expected
    assert fake_agent.received_options == {
        "response_format": RequirementAnalysis
    }


@pytest.mark.asyncio
async def test_analyze_validates_dictionary_output() -> None:
    expected = valid_analysis()
    fake_agent = FakeAgent(value=expected.model_dump())
    agent = RequirementsAnalysisAgent(agent=fake_agent)

    result = await agent.analyze("Build a PDF processing application.")

    assert result == expected


@pytest.mark.asyncio
async def test_analyze_parses_json_text_fallback() -> None:
    expected = valid_analysis()
    fake_agent = FakeAgent(
        value=None,
        text=expected.model_dump_json(),
    )
    agent = RequirementsAnalysisAgent(agent=fake_agent)

    result = await agent.analyze("Build a PDF processing application.")

    assert result == expected


@pytest.mark.asyncio
async def test_analyze_rejects_empty_requirements() -> None:
    fake_agent = FakeAgent(value=valid_analysis())
    agent = RequirementsAnalysisAgent(agent=fake_agent)

    with pytest.raises(ValueError, match="must not be empty"):
        await agent.analyze("   ")
