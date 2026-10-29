
from typing import Any, cast
from types import SimpleNamespace

import pytest

from app.api.schemas import (
    ArchitectureDesign,
    ArchitectureResponse,
    ArchitectureReview,
    RequirementAnalysis,
)
from app.orchestrator import architecture_orchestrator as module
from app.orchestrator.architecture_orchestrator import ArchitectureOrchestrator


def make_response(with_review: bool = True) -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureDelegationCoordinator",
        model_provider="openai",
        requirements_analysis=RequirementAnalysis(
            functional_requirements=["Users can upload documents."],
            non_functional_requirements=["Data must be protected."],
            assumptions=[],
            open_questions=[],
            constraints=["Local deployment."],
        ),
        architecture=ArchitectureDesign(
            summary="A document processing application.",
            components=[],
            data_flow=["Client submits a document to the API."],
            mermaid_diagram='flowchart LR\n client["Client"] --> api["API"]',
        ),
        decisions=[],
        risks=[],
        next_steps=["Build a proof of concept."],
        review=(
            ArchitectureReview(
                summary="Review completed.",
                findings=[],
                approval_recommendation="approve",
            )
            if with_review
            else None
        ),
    )


class FakeParentAgent:
    def __init__(self, *, tools: list[Any], response: Any) -> None:
        self.tools = tools
        self.response = response
        self.prompt: str | None = None
        self.options: dict[str, Any] | None = None

    async def run(
        self,
        prompt: str,
        *,
        options: dict[str, Any],
        function_invocation_kwargs: dict[str, Any] | None = None,
    ) -> Any:
        self.prompt = prompt
        self.options = options
        return SimpleNamespace(value=self.response)


@pytest.mark.asyncio
async def test_delegation_registers_specialist_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_response()
    created: dict[str, Any] = {}

    def fake_agent_factory(**kwargs: Any) -> FakeParentAgent:
        created.update(kwargs)
        return FakeParentAgent(
            tools=kwargs["tools"],
            response=expected,
        )

    monkeypatch.setattr(module, "Agent", fake_agent_factory)
    monkeypatch.setattr(module, "create_model_client", lambda: object())

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, object()),
        architecture_agent=cast(Any, object()),
        architecture_review_agent=cast(Any, object()),
    )

    result = await orchestrator.design_with_delegation(
        "Build a document processing API.",
        "openai",
    )

    assert result == expected
    assert created["name"] == "ArchitectureDelegationCoordinator"
    assert [tool.name for tool in created["tools"]] == [
        "analyze_software_requirements",
        "design_software_architecture",
        "review_software_architecture",
    ]
    delegation_agent = orchestrator._delegation_agent
    assert isinstance(delegation_agent, FakeParentAgent)
    assert delegation_agent.prompt is not None
    assert "Configured model provider: openai" in delegation_agent.prompt


@pytest.mark.asyncio
async def test_delegation_rejects_architecture_without_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_agent_factory(**kwargs: Any) -> FakeParentAgent:
        return FakeParentAgent(
            tools=kwargs["tools"],
            response=make_response(with_review=False),
        )

    monkeypatch.setattr(module, "Agent", fake_agent_factory)
    monkeypatch.setattr(module, "create_model_client", lambda: object())

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, object()),
        architecture_agent=cast(Any, object()),
        architecture_review_agent=cast(Any, object()),
    )

    with pytest.raises(RuntimeError, match="without a review"):
        await orchestrator.design_with_delegation(
            "Build a document processing API.",
            "openai",
        )


@pytest.mark.asyncio
async def test_delegation_fallback_reviews_returned_architecture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_response(with_review=False)

    def fake_agent_factory(**kwargs: Any) -> FakeParentAgent:
        return FakeParentAgent(
            tools=kwargs["tools"],
            response=expected,
        )

    class FakeReviewAgent:
        async def review(
            self,
            response: ArchitectureResponse,
        ) -> ArchitectureReview:
            return ArchitectureReview(
                summary="Fallback review completed.",
                findings=[],
                approval_recommendation="approve",
            )

    monkeypatch.setattr(module, "Agent", fake_agent_factory)
    monkeypatch.setattr(module, "create_model_client", lambda: object())

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, object()),
        architecture_agent=cast(Any, object()),
        architecture_review_agent=cast(Any, FakeReviewAgent()),
    )

    result = await orchestrator.design_with_delegation(
        "Build a document processing API.",
        "openai",
    )

    assert result.review is not None
    assert result.review.summary == "Fallback review completed."
