
import logging
from dataclasses import dataclass
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.requirements_agent import RequirementsAnalysisAgent
from app.api.schemas import ArchitectureResponse, RequirementAnalysis

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchitectureWorkflowInput:
    requirements: str
    model_provider: str


@dataclass(frozen=True)
class RequirementsAnalysisEnvelope:
    requirements: str
    model_provider: str
    analysis: RequirementAnalysis


class RequirementsAnalysisExecutor(Executor):
    """Runs the Requirements Analysis Agent as a MAF workflow stage."""

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
    """Runs the Architecture Agent and yields the final response."""

    def __init__(self, architecture_agent: ArchitectureAgent) -> None:
        super().__init__(id="architecture_design")
        self._architecture_agent = architecture_agent

    @handler
    async def process(self, envelope: RequirementsAnalysisEnvelope, 
                      ctx: WorkflowContext[Never, ArchitectureResponse]) -> None:
        logger.info("event=maf_architecture_design_started")

        response = await self._architecture_agent.design(
            requirements=envelope.requirements,
            model_provider=envelope.model_provider,
            requirements_analysis=envelope.analysis,
        )

        logger.info("event=maf_architecture_design_completed")

        await ctx.yield_output(response)


class ArchitectureOrchestrator:
    """Builds and executes the MAF architecture-generation workflow."""

    def __init__(self, requirements_agent: RequirementsAnalysisAgent | None = None, 
                 architecture_agent: ArchitectureAgent | None = None) -> None:
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

    def _build_workflow(self):
        requirements_executor = RequirementsAnalysisExecutor(
            self._requirements_agent
        )
        
        architecture_executor = ArchitectureDesignExecutor(
            self._architecture_agent
        )

        return (
            WorkflowBuilder(start_executor=requirements_executor)
            .add_edge(requirements_executor, architecture_executor)
            .build()
        )

    async def design(self, requirements: str, model_provider: str) -> ArchitectureResponse:
        """Execute the typed MAF workflow and return its final output."""

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

        return response