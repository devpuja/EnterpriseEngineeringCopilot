from typing import Any, cast

import pytest

from app.agents.delegation_tools import AgentDelegationTools
from app.api.schemas import (
    ArchitectureDesign,
    ArchitectureResponse,
    ArchitectureReview,
    RequirementAnalysis,
)


def create_analysis() -> RequirementAnalysis:
    return RequirementAnalysis(
        functional_requirements=["Users can upload documents."],
        non_functional_requirements=["Documents must be protected."],
        assumptions=[],
        open_questions=[],
        constraints=["Use a local deployment."],
    )


def create_response() -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="openai",
        requirements_analysis=create_analysis(),
        architecture=ArchitectureDesign(
            summary="A document processing application.",
            components=[],
            data_flow=["Client submits a document to the API."],
            mermaid_diagram='flowchart LR\n client["Client"] --> api["API"]',
        ),
        decisions=[],
        risks=[],
        next_steps=["Build a proof of concept."],
    )


class FakeRequirementsAgent:
    def __init__(self) -> None:
        self.received: str | None = None

    async def analyze(self, requirements: str) -> RequirementAnalysis:
        self.received = requirements
        return create_analysis()


class FakeArchitectureAgent:
    def __init__(self) -> None:
        self.received: dict[str, Any] | None = None

    async def design(self, **kwargs: Any) -> ArchitectureResponse:
        self.received = kwargs
        return create_response().model_copy(
            update={"review": ArchitectureReview(
                summary="Stale review must be cleared.",
                findings=[],
                approval_recommendation="approve",
            )}
        )


class FakeReviewAgent:
    def __init__(self) -> None:
        self.received: ArchitectureResponse | None = None

    async def review(self, response: ArchitectureResponse) -> ArchitectureReview:
        self.received = response
        return ArchitectureReview(
            summary="Review completed.",
            findings=[],
            approval_recommendation="approve",
        )


@pytest.fixture
def delegation() -> tuple[AgentDelegationTools, FakeRequirementsAgent, FakeArchitectureAgent, FakeReviewAgent]:
    requirements_agent = FakeRequirementsAgent()
    architecture_agent = FakeArchitectureAgent()
    review_agent = FakeReviewAgent()
    tools = AgentDelegationTools(
        requirements_agent=cast(Any, requirements_agent),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, review_agent),
    )
    return tools, requirements_agent, architecture_agent, review_agent


@pytest.mark.asyncio
async def test_requirements_delegation_returns_validated_json(delegation: Any) -> None:
    tools, requirements_agent, _, _ = delegation
    result = await tools.analyze_requirements("  Build a document processing API.  ")

    assert RequirementAnalysis.model_validate_json(result) == create_analysis()
    assert requirements_agent.received == "Build a document processing API."


@pytest.mark.asyncio
async def test_requirements_delegation_rejects_empty_or_oversized_input(delegation: Any) -> None:
    tools, *_ = delegation
    with pytest.raises(ValueError, match="must not be empty"):
        await tools.analyze_requirements("  ")
    with pytest.raises(ValueError, match="12000"):
        await tools.analyze_requirements("x" * 12_001)


@pytest.mark.asyncio
async def test_design_delegation_passes_analysis_and_clears_old_review(delegation: Any) -> None:
    tools, _, architecture_agent, _ = delegation
    analysis_json = create_analysis().model_dump_json()
    result_json = await tools.design_architecture(
        requirements="Build a document processing API.",
        model_provider=" OPENAI ",
        requirements_analysis_json=analysis_json,
    )
    result = ArchitectureResponse.model_validate_json(result_json)

    assert architecture_agent.received is not None
    assert architecture_agent.received["model_provider"] == "openai"
    assert architecture_agent.received["requirements_analysis"] == create_analysis()
    assert result.review is None


@pytest.mark.asyncio
async def test_design_delegation_rejects_invalid_analysis_json(delegation: Any) -> None:
    tools, *_ = delegation
    with pytest.raises(ValueError, match="valid RequirementAnalysis"):
        await tools.design_architecture(
            requirements="Build a document processing API.",
            model_provider="openai",
            requirements_analysis_json="{invalid",
        )


@pytest.mark.asyncio
async def test_review_delegation_validates_architecture_and_returns_review_json(delegation: Any) -> None:
    tools, _, _, review_agent = delegation
    response = create_response()
    review_json = await tools.review_architecture(response.model_dump_json())

    assert ArchitectureReview.model_validate_json(review_json).approval_recommendation == "approve"
    assert review_agent.received is not None
    assert review_agent.received.architecture == response.architecture


@pytest.mark.asyncio
async def test_review_delegation_rejects_invalid_architecture_json(delegation: Any) -> None:
    tools, *_ = delegation
    with pytest.raises(ValueError, match="valid ArchitectureResponse"):
        await tools.review_architecture("not-json")


@pytest.mark.asyncio
async def test_review_delegation_recovers_cached_design(delegation: Any) -> None:
    tools, _, _, review_agent = delegation

    await tools.design_architecture(
        requirements="Build a document processing API.",
        model_provider="openai",
        requirements_analysis_json=create_analysis().model_dump_json(),
    )

    review_json = await tools.review_architecture('{"agent":"truncated"')

    assert ArchitectureReview.model_validate_json(
        review_json
    ).approval_recommendation == "approve"
    assert review_agent.received is not None


def test_delegation_tools_have_stable_names_and_are_registered(delegation: Any) -> None:
    tools, *_ = delegation
    registered_tools = tools.build_tools()
    assert [tool.name for tool in registered_tools] == [
        "analyze_software_requirements",
        "design_software_architecture",
        "review_software_architecture",
    ]
