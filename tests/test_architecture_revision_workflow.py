
import pytest
from typing import Any, Literal, cast

from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDecision,
    ArchitectureDesign,
    ArchitectureResponse,
    ArchitectureReview,
    ArchitectureReviewFinding,
    RequirementAnalysis,
)
from app.orchestrator.architecture_orchestrator import (
    ArchitectureOrchestrator,
    MAX_ARCHITECTURE_REVISIONS,
)


def make_review(
    recommendation: Literal["approve", "revise", "needs_human_review"],
) -> ArchitectureReview:
    findings = list[ArchitectureReviewFinding]()

    if recommendation == "revise":
        findings.append(
            ArchitectureReviewFinding(
                severity="medium",
                category="maintainability",
                finding="Clarify component responsibilities.",
                evidence="The component responsibilities need more detail.",
                recommendation="Clarify the API component's responsibilities.",
            )
        )

    return ArchitectureReview(
        summary=f"Test review: {recommendation}",
        findings=findings,
        approval_recommendation=recommendation,
    )


class FakeRequirementsAgent:
    async def analyze(self, requirements: str) -> RequirementAnalysis:
        return RequirementAnalysis(
            functional_requirements=["Users can submit requests."],
            non_functional_requirements=[],
            assumptions=[],
            open_questions=[],
            constraints=[],
        )


class FakeArchitectureAgent:
    def __init__(self):
        self.design_calls = 0
        self.review_feedback_received: list[ArchitectureReview | None] = []

    async def design(
        self,
        requirements: str,
        model_provider: str,
        requirements_analysis: RequirementAnalysis | None = None,
        review_feedback: ArchitectureReview | None = None,
    ) -> ArchitectureResponse:
        self.design_calls += 1
        self.review_feedback_received.append(review_feedback)

        analysis = requirements_analysis or RequirementAnalysis(
            functional_requirements=[],
            non_functional_requirements=[],
            assumptions=[],
            open_questions=[],
            constraints=[],
        )

        return ArchitectureResponse(
            agent="ArchitectureAgent",
            model_provider=model_provider,
            requirements_analysis=analysis,
            architecture=ArchitectureDesign(
                summary="A simple API architecture.",
                components=[
                    ArchitectureComponent(
                        name="API",
                        responsibility="Handles incoming requests.",
                        technology="FastAPI",
                        rationale="Provides an HTTP interface.",
                    )
                ],
                data_flow=["User sends a request to the API."],
                mermaid_diagram=(
                    'flowchart LR\n'
                    '    User["User"] --> api["API"]'
                ),
            ),
            decisions=[
                ArchitectureDecision(
                    decision="Use an API.",
                    rationale="Provides a request interface.",
                    alternatives=["Command-line interface"],
                    trade_offs=["Requires API hosting."],
                )
            ],
            risks=[],
            next_steps=[],
        )


class FakeArchitectureReviewAgent:
    def __init__(
        self,
        recommendations: list[Literal["approve", "revise", "needs_human_review"]],
    ):
        self.reviews = [make_review(item) for item in recommendations]
        self.review_calls = 0

    async def review(self, response: ArchitectureResponse) -> ArchitectureReview:
        review = self.reviews[self.review_calls]
        self.review_calls += 1
        return review


@pytest.mark.asyncio
async def test_approved_design_finishes_without_revision():
    architecture_agent = FakeArchitectureAgent()
    reviewer = FakeArchitectureReviewAgent(["approve"])

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, FakeRequirementsAgent()),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, reviewer),
    )

    result = await orchestrator.design(
        requirements="Users can submit requests through an API.",
        model_provider="openai",
    )

    assert result.review is not None
    assert result.review.approval_recommendation == "approve"
    assert architecture_agent.design_calls == 1
    assert reviewer.review_calls == 1
    assert architecture_agent.review_feedback_received == [None]


@pytest.mark.asyncio
async def test_revision_then_approval_finishes_after_second_review():
    architecture_agent = FakeArchitectureAgent()
    reviewer = FakeArchitectureReviewAgent(["revise", "approve"])

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, FakeRequirementsAgent()),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, reviewer),
    )

    result = await orchestrator.design(
        requirements="Users can submit requests through an API.",
        model_provider="openai",
    )

    assert result.review is not None
    assert result.review.approval_recommendation == "approve"
    assert architecture_agent.design_calls == 2
    assert reviewer.review_calls == 2
    assert architecture_agent.review_feedback_received[0] is None
    assert architecture_agent.review_feedback_received[1] is not None


@pytest.mark.asyncio
async def test_revision_limit_stops_another_revision():
    architecture_agent = FakeArchitectureAgent()
    reviewer = FakeArchitectureReviewAgent(["revise", "revise"])

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, FakeRequirementsAgent()),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, reviewer),
    )

    result = await orchestrator.design(
        requirements="Users can submit requests through an API.",
        model_provider="openai",
    )

    assert result.review is not None
    assert result.review.approval_recommendation == "revise"
    assert architecture_agent.design_calls == 1 + MAX_ARCHITECTURE_REVISIONS
    assert reviewer.review_calls == 1 + MAX_ARCHITECTURE_REVISIONS


@pytest.mark.asyncio
async def test_human_review_recommendation_does_not_trigger_revision():
    architecture_agent = FakeArchitectureAgent()
    reviewer = FakeArchitectureReviewAgent(["needs_human_review"])

    orchestrator = ArchitectureOrchestrator(
        requirements_agent=cast(Any, FakeRequirementsAgent()),
        architecture_agent=cast(Any, architecture_agent),
        architecture_review_agent=cast(Any, reviewer),
    )

    result = await orchestrator.design(
        requirements="Users can submit requests through an API.",
        model_provider="openai",
    )

    assert result.review is not None
    assert result.review.approval_recommendation == "needs_human_review"
    assert architecture_agent.design_calls == 1
    assert reviewer.review_calls == 1