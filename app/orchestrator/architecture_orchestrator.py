
import logging
from dataclasses import dataclass
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.architecture_review_agent import ArchitectureReviewAgent
from app.agents.requirements_agent import RequirementsAnalysisAgent
from app.api.schemas import (
    ArchitectureResponse,
    ArchitectureReview,
    RequirementAnalysis,
)
from app.services.azure_pdf_reference_architecture import (
    build_azure_pdf_reference_architecture,
    matches_azure_pdf_platform,
)
from app.services.diagram_validator import validate_mermaid_flowchart

logger = logging.getLogger(__name__)

MAX_ARCHITECTURE_REVISIONS = 2


@dataclass(frozen=True)
class ArchitectureWorkflowInput:
    requirements: str
    model_provider: str


@dataclass(frozen=True)
class RequirementsAnalysisEnvelope:
    requirements: str
    model_provider: str
    analysis: RequirementAnalysis


@dataclass(frozen=True)
class ArchitectureReviewEnvelope:
    requirements: str
    model_provider: str
    analysis: RequirementAnalysis
    response: ArchitectureResponse
    revision_count: int = 0


def should_revise(envelope: ArchitectureReviewEnvelope) -> bool:
    """Return True only when a revision is requested and attempts remain."""
    review = envelope.response.review

    return (
        review is not None
        and review.approval_recommendation == "revise"
        and envelope.revision_count < MAX_ARCHITECTURE_REVISIONS
    )


class RequirementsAnalysisExecutor(Executor):
    def __init__(self, requirements_agent: RequirementsAnalysisAgent) -> None:
        super().__init__(id="requirements_analysis")
        self._requirements_agent = requirements_agent

    @handler
    async def process(
        self,
        request: ArchitectureWorkflowInput,
        ctx: WorkflowContext[RequirementsAnalysisEnvelope],
    ) -> None:
        logger.info("event=maf_requirements_analysis_started")

        analysis = await self._requirements_agent.analyze(
            request.requirements
        )

        logger.info(
            "event=maf_requirements_analysis_completed "
            "functional_count=%d non_functional_count=%d",
            len(analysis.functional_requirements),
            len(analysis.non_functional_requirements),
        )

        await ctx.send_message(
            RequirementsAnalysisEnvelope(
                requirements=request.requirements,
                model_provider=request.model_provider,
                analysis=analysis,
            )
        )


class ArchitectureDesignExecutor(Executor):
    def __init__(self, architecture_agent: ArchitectureAgent) -> None:
        super().__init__(id="architecture_design")
        self._architecture_agent = architecture_agent

    @handler
    async def process(
        self,
        envelope: RequirementsAnalysisEnvelope,
        ctx: WorkflowContext[ArchitectureReviewEnvelope],
    ) -> None:
        logger.info("event=maf_architecture_design_started")

        response = await self._architecture_agent.design(
            requirements=envelope.requirements,
            model_provider=envelope.model_provider,
            requirements_analysis=envelope.analysis,
        )

        # A new design must not inherit an old review.
        response = response.model_copy(update={"review": None})

        logger.info("event=maf_architecture_design_completed")

        await ctx.send_message(
            ArchitectureReviewEnvelope(
                requirements=envelope.requirements,
                model_provider=envelope.model_provider,
                analysis=envelope.analysis,
                response=response,
                revision_count=0,
            )
        )


class ArchitectureReviewExecutor(Executor):
    def __init__(
        self,
        architecture_review_agent: ArchitectureReviewAgent,
    ) -> None:
        super().__init__(id="architecture_review")
        self._architecture_review_agent = architecture_review_agent

    @handler
    async def process(
        self,
        envelope: ArchitectureReviewEnvelope,
        ctx: WorkflowContext[ArchitectureReviewEnvelope],
    ) -> None:
        logger.info(
            "event=maf_architecture_review_started revision_count=%d",
            envelope.revision_count,
        )

        review: ArchitectureReview = (
            await self._architecture_review_agent.review(envelope.response)
        )

        reviewed_response = envelope.response.model_copy(
            update={"review": review}
        )

        reviewed_envelope = ArchitectureReviewEnvelope(
            requirements=envelope.requirements,
            model_provider=envelope.model_provider,
            analysis=envelope.analysis,
            response=reviewed_response,
            revision_count=envelope.revision_count,
        )

        logger.info(
            "event=maf_architecture_review_completed "
            "revision_count=%d findings=%d recommendation=%s",
            reviewed_envelope.revision_count,
            len(review.findings),
            review.approval_recommendation,
        )

        # Conditional outgoing edges decide whether to revise or finish.
        await ctx.send_message(reviewed_envelope)


class ArchitectureRevisionExecutor(Executor):
    def __init__(self, architecture_agent: ArchitectureAgent) -> None:
        super().__init__(id="architecture_revision")
        self._architecture_agent = architecture_agent

    @handler
    async def process(
        self,
        envelope: ArchitectureReviewEnvelope,
        ctx: WorkflowContext[ArchitectureReviewEnvelope],
    ) -> None:
        feedback = envelope.response.review

        if feedback is None:
            raise RuntimeError(
                "Cannot revise an architecture without review feedback."
            )

        if envelope.revision_count >= MAX_ARCHITECTURE_REVISIONS:
            raise RuntimeError(
                "Architecture revision limit has already been reached."
            )

        logger.info(
            "event=maf_architecture_revision_started "
            "revision_count=%d",
            envelope.revision_count + 1,
        )

        revised_response = await self._architecture_agent.design(
            requirements=envelope.requirements,
            model_provider=envelope.model_provider,
            requirements_analysis=envelope.analysis,
            review_feedback=feedback,
            previous_response=envelope.response,
        )

        # The revised design must be reviewed again.
        revised_response = revised_response.model_copy(
            update={"review": None}
        )

        revised_envelope = ArchitectureReviewEnvelope(
            requirements=envelope.requirements,
            model_provider=envelope.model_provider,
            analysis=envelope.analysis,
            response=revised_response,
            revision_count=envelope.revision_count + 1,
        )

        logger.info(
            "event=maf_architecture_revision_completed "
            "revision_count=%d",
            revised_envelope.revision_count,
        )

        await ctx.send_message(revised_envelope)


class ArchitectureFinalizeExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="architecture_finalize")

    @handler
    async def process(
        self,
        envelope: ArchitectureReviewEnvelope,
        ctx: WorkflowContext[Never, ArchitectureResponse],
    ) -> None:
        if envelope.response.review is None:
            raise RuntimeError(
                "Cannot finalize an architecture without a review."
            )

        logger.info(
            "event=maf_architecture_finalized "
            "revision_count=%d recommendation=%s",
            envelope.revision_count,
            envelope.response.review.approval_recommendation,
        )

        await ctx.yield_output(envelope.response)


class ArchitectureOrchestrator:
    def __init__(
        self,
        requirements_agent: RequirementsAnalysisAgent | None = None,
        architecture_agent: ArchitectureAgent | None = None,
        architecture_review_agent: ArchitectureReviewAgent | None = None,
    ) -> None:
        self._requirements_agent = (
            requirements_agent
            if requirements_agent is not None
            else RequirementsAnalysisAgent()
        )
        self._architecture_agent = (
            architecture_agent
            if architecture_agent is not None
            else ArchitectureAgent()
        )
        self._architecture_review_agent = (
            architecture_review_agent
            if architecture_review_agent is not None
            else ArchitectureReviewAgent()
        )

    def _build_workflow(self):
        requirements_executor = RequirementsAnalysisExecutor(
            self._requirements_agent
        )
        architecture_executor = ArchitectureDesignExecutor(
            self._architecture_agent
        )
        review_executor = ArchitectureReviewExecutor(
            self._architecture_review_agent
        )
        revision_executor = ArchitectureRevisionExecutor(
            self._architecture_agent
        )
        finalize_executor = ArchitectureFinalizeExecutor()

        return (
            WorkflowBuilder(start_executor=requirements_executor)
            .add_edge(requirements_executor, architecture_executor)
            .add_edge(architecture_executor, review_executor)
            .add_edge(
                review_executor,
                revision_executor,
                condition=should_revise,
            )
            .add_edge(
                review_executor,
                finalize_executor,
                condition=lambda envelope: not should_revise(envelope),
            )
            .add_edge(revision_executor, review_executor)
            .build()
        )

    async def design(
        self,
        requirements: str,
        model_provider: str,
    ) -> ArchitectureResponse:
        if matches_azure_pdf_platform(requirements):
            logger.info("event=azure_pdf_reference_architecture_selected")
            analysis = await self._requirements_agent.analyze(requirements)
            response = build_azure_pdf_reference_architecture(
                requirements_analysis=analysis,
                model_provider=model_provider.lower(),
            )
            diagram_errors = validate_mermaid_flowchart(
                response.architecture.mermaid_diagram
            )
            if diagram_errors:
                raise RuntimeError(
                    "The Azure PDF reference architecture contains an invalid "
                    "Mermaid diagram: " + "; ".join(diagram_errors)
                )
            return response

        workflow = self._build_workflow()

        result = await workflow.run(
            ArchitectureWorkflowInput(
                requirements=requirements,
                model_provider=model_provider.lower(),
            )
        )

        outputs = result.get_outputs()

        if not outputs:
            raise RuntimeError(
                "The MAF workflow completed without producing an output."
            )

        response = outputs[0]

        if not isinstance(response, ArchitectureResponse):
            raise RuntimeError(
                "The MAF workflow returned an unexpected output type."
            )

        if response.review is None:
            raise RuntimeError(
                "The MAF workflow completed without an architecture review."
            )

        return response