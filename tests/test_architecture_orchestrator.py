
from typing import Any, cast

import pytest

from app.api.schemas import (
    ArchitectureDesign,
    ArchitectureReview,
    ArchitectureResponse,
    RequirementAnalysis,
)
from app.orchestrator.architecture_orchestrator import ArchitectureOrchestrator


def create_analysis() -> RequirementAnalysis:
    return RequirementAnalysis(
        functional_requirements=["Users can upload PDF documents."],
        non_functional_requirements=["Tenant data must be isolated."],
        assumptions=["Users are authenticated."],
        open_questions=["What is the maximum file size?"],
        constraints=["Use Microsoft Azure."],
    )


def create_response(analysis: RequirementAnalysis) -> ArchitectureResponse:
    return ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider="openai",
        requirements_analysis=analysis,
        architecture=ArchitectureDesign(
            summary="A PDF processing application.",
            components=[],
            data_flow=[],
            mermaid_diagram=(
                "flowchart LR\n"
                'client["Client"] --> api["API"]'
            ),
        ),
        decisions=[],
        risks=[],
        next_steps=["Build a proof of concept."],
    )


class FakeRequirementsAgent:
    def __init__(self, analysis: RequirementAnalysis) -> None:
        self.analysis = analysis
        self.received_requirements: str | None = None

    async def analyze(self, requirements: str) -> RequirementAnalysis:
        self.received_requirements = requirements
        return self.analysis


class FakeArchitectureAgent:
    def __init__(self, response: ArchitectureResponse) -> None:
        self.response = response
        self.received_requirements: str | None = None
        self.received_provider: str | None = None
        self.received_analysis: RequirementAnalysis | None = None

    async def design(
        self,
        requirements: str,
        model_provider: str,
        requirements_analysis: RequirementAnalysis | None = None,
    ) -> ArchitectureResponse:
        self.received_requirements = requirements
        self.received_provider = model_provider
        self.received_analysis = requirements_analysis
        return self.response


class FakeArchitectureReviewAgent:
    def __init__(self, review: ArchitectureReview) -> None:
        self.review_result = review
        self.received_response: ArchitectureResponse | None = None

    async def review(self, response: ArchitectureResponse) -> ArchitectureReview:
        self.received_response = response
        return self.review_result


@pytest.mark.asyncio
async def test_orchestrator_passes_analysis_to_architecture_agent() -> None:
    requirements = "Build an Azure application for PDF processing."
    analysis = create_analysis()
    expected_response = create_response(analysis)

    requirements_agent = FakeRequirementsAgent(analysis)
    architecture_agent = FakeArchitectureAgent(expected_response)
    review = ArchitectureReview(
        summary="The proposed architecture passed the test review.",
        findings=[],
        approval_recommendation="approve",
    )
    architecture_review_agent = FakeArchitectureReviewAgent(review)

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, requirements_agent),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, architecture_review_agent),
    )

    result = await orchestrator.design(
        requirements=requirements,
        model_provider="openai",
    )

    assert result is not expected_response
    assert result.architecture == expected_response.architecture
    assert requirements_agent.received_requirements == requirements
    assert architecture_agent.received_requirements == requirements
    assert architecture_agent.received_provider == "openai"
    assert architecture_agent.received_analysis == analysis
    assert result.review == review
    assert architecture_review_agent.received_response == expected_response
    assert architecture_review_agent.received_response is not None
    assert architecture_review_agent.received_response.review is None


@pytest.mark.asyncio
async def test_orchestrator_stops_if_requirements_analysis_fails() -> None:
    class FailingRequirementsAgent:
        received_requirements: str | None = None

        async def analyze(self, requirements: str) -> RequirementAnalysis:
            self.received_requirements = requirements
            raise ValueError("Requirements analysis failed.")

    analysis = create_analysis()
    requirements_agent = FailingRequirementsAgent()
    architecture_agent = FakeArchitectureAgent(create_response(analysis))

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, requirements_agent),
        architecture_agent=cast(Any, architecture_agent),
    )

    requirements = "Build a PDF processing application."
    with pytest.raises(ValueError, match="Requirements analysis failed"):
        await orchestrator.design(
            requirements=requirements,
            model_provider="openai",
        )

    assert requirements_agent.received_requirements == requirements
    assert architecture_agent.received_requirements is None