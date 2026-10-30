
from typing import Any, cast
from types import SimpleNamespace

import pytest
import json

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
    def __init__(
        self,
        *,
        tools: list[Any],
        response: Any,
        run_callback: Any | None = None,
    ) -> None:
        self.tools = tools
        self.response = response
        self.prompt: str | None = None
        self.options: dict[str, Any] | None = None
        self.run_callback = run_callback

    async def run(
        self,
        prompt: str,
        *,
        options: dict[str, Any],
        function_invocation_kwargs: dict[str, Any] | None = None,
    ) -> Any:
        self.prompt = prompt
        self.options = options
        if self.run_callback is not None:
            await self.run_callback()
        return SimpleNamespace(value=self.response)


@pytest.mark.asyncio
async def test_delegation_registers_specialist_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_response()
    created: dict[str, Any] = {}

    class FakeRequirementsAgent:
        async def analyze(self, requirements: str) -> RequirementAnalysis:
            return expected.requirements_analysis

    class FakeArchitectureAgent:
        async def design(self, **kwargs: Any) -> ArchitectureResponse:
            return expected.model_copy(update={"review": None})

    class FakeReviewAgent:
        async def review(
            self,
            response: ArchitectureResponse,
        ) -> ArchitectureReview:
            return expected.review

    orchestrator_holder: dict[str, ArchitectureOrchestrator] = {}

    def fake_agent_factory(**kwargs: Any) -> FakeParentAgent:
        created.update(kwargs)

        async def run_tools() -> None:
            orchestrator = orchestrator_holder["orchestrator"]
            design_json = await orchestrator._delegation_tools.design_architecture(
                requirements="Build a document processing API.",
                model_provider="openai",
                requirements_analysis_json=expected.requirements_analysis.model_dump_json(),
            )
            architecture_id = json.loads(design_json)["architecture_id"]
            await orchestrator._delegation_tools.review_architecture(architecture_id)

        return FakeParentAgent(
            tools=kwargs["tools"],
            response=expected,
            run_callback=run_tools,
        )

    monkeypatch.setattr(module, "Agent", fake_agent_factory)
    monkeypatch.setattr(module, "create_model_client", lambda: object())

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, FakeRequirementsAgent()),
        architecture_agent=cast(Any, FakeArchitectureAgent()),
        architecture_review_agent=cast(Any, FakeReviewAgent()),
    )
    orchestrator_holder["orchestrator"] = orchestrator

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

    with pytest.raises(RuntimeError, match="review"):
        await orchestrator.design_with_delegation(
            "Build a document processing API.",
            "openai",
        )


@pytest.mark.asyncio
async def test_delegation_does_not_fallback_to_unverified_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_response(with_review=False)

    def fake_agent_factory(**kwargs: Any) -> FakeParentAgent:
        return FakeParentAgent(
            tools=kwargs["tools"],
            response=expected,
        )

    class FakeReviewAgent:
        called = False

        async def review(
            self,
            response: ArchitectureResponse,
        ) -> ArchitectureReview:
            self.called = True
            return ArchitectureReview(
                summary="Fallback review completed.",
                findings=[],
                approval_recommendation="approve",
            )

    monkeypatch.setattr(module, "Agent", fake_agent_factory)
    monkeypatch.setattr(module, "create_model_client", lambda: object())

    review_agent = FakeReviewAgent()
    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, object()),
        architecture_agent=cast(Any, object()),
        architecture_review_agent=cast(Any, review_agent),
    )

    with pytest.raises(RuntimeError, match="review"):
        await orchestrator.design_with_delegation(
            "Build a document processing API.",
            "openai",
        )

    assert review_agent.called is False
