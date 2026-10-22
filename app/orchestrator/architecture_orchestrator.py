
import logging

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.requirements_agent import RequirementsAnalysisAgent
from app.api.schemas import ArchitectureResponse

logger = logging.getLogger(__name__)


class ArchitectureOrchestrator:
    """Coordinates requirements analysis and architecture generation."""

    def __init__(
        self,
        requirements_agent: RequirementsAnalysisAgent | None = None,
        architecture_agent: ArchitectureAgent | None = None,
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

    async def design(
        self,
        requirements: str,
        model_provider: str,
    ) -> ArchitectureResponse:
        """Run requirements analysis, then generate the architecture."""

        logger.info("event=requirements_analysis_started")

        analysis = await self._requirements_agent.analyze(requirements)

        logger.info(
            "event=requirements_analysis_completed "
            "functional_count=%d non_functional_count=%d "
            "constraint_count=%d open_question_count=%d",
            len(analysis.functional_requirements),
            len(analysis.non_functional_requirements),
            len(analysis.constraints),
            len(analysis.open_questions),
        )

        logger.info("event=architecture_design_started")

        response = await self._architecture_agent.design(
            requirements=requirements,
            model_provider=model_provider,
            requirements_analysis=analysis,
        )

        logger.info("event=architecture_design_completed")

        return response