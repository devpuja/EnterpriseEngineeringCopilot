"""Explicit, schema-described delegation tools for specialist agents.

These wrappers let a parent Microsoft Agent Framework agent invoke the
existing requirements, architecture-design, and architecture-review agents
as tools. They do not replace the current workflow orchestrator.
"""

import json
import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field, ValidationError

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.architecture_review_agent import ArchitectureReviewAgent
from app.agents.requirements_agent import RequirementsAnalysisAgent
from app.api.schemas import (
    ArchitectureResponse,
    ArchitectureReview,
    RequirementAnalysis,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AgentDelegationTools:
    """Build callable MAF tools around the existing specialist agents.

    Tool contracts deliberately use JSON strings for structured outputs so
    the parent agent can pass one specialist's result to the next tool without
    relying on provider-specific rich-content serialization.
    """

    def __init__(
        self,
        requirements_agent: RequirementsAnalysisAgent,
        architecture_agent: ArchitectureAgent,
        architecture_review_agent: ArchitectureReviewAgent,
    ) -> None:
        self._requirements_agent = requirements_agent
        self._architecture_agent = architecture_agent
        self._architecture_review_agent = architecture_review_agent
        self._reviewed_responses: dict[str, ArchitectureReview] = {}
        self._last_requirements: str | None = None
        self._last_architecture_response: ArchitectureResponse | None = None

    @staticmethod
    def _architecture_key(response: ArchitectureResponse) -> str:
        return response.model_copy(update={"review": None}).model_dump_json()

    def attach_review(self, response: ArchitectureResponse) -> ArchitectureResponse:
        """Attach a review captured by the review specialist, when available."""
        review = self._reviewed_responses.get(self._architecture_key(response))
        if review is not None:
            return response.model_copy(update={"review": review})
        return response

    async def analyze_requirements(self, requirements: str) -> str:
        """Analyze requirements and return validated RequirementAnalysis JSON."""
        if not requirements or not requirements.strip():
            raise ValueError("requirements must not be empty")
        if len(requirements) > 12_000:
            raise ValueError("requirements must not exceed 12000 characters")

        try:
            analysis = await self._requirements_agent.analyze(requirements.strip())
        except Exception:
            logger.exception(
                "event=agent_delegation_failed specialist=requirements_analysis"
            )
            raise

        self._last_requirements = requirements.strip()
        logger.info("event=agent_delegation_completed specialist=requirements_analysis")
        return analysis.model_dump_json()

    async def design_architecture(
        self,
        requirements: Any = "",
        model_provider: Any = "",
        requirements_analysis_json: Any = "",
    ) -> str:
        """Design architecture, optionally using JSON from requirements analysis."""
        logger.info(
            "event=agent_delegation_input_received "
            "specialist=architecture_design requirements_length=%d "
            "model_provider_present=%s analysis_input_type=%s "
            "analysis_json_length=%d",
            len(requirements) if isinstance(requirements, str) else 0,
            isinstance(model_provider, str) and bool(model_provider.strip()),
            type(requirements_analysis_json).__name__,
            len(requirements_analysis_json)
            if isinstance(requirements_analysis_json, str)
            else 0,
        )

        if not isinstance(requirements, str):
            requirements = ""
        requirements = requirements.strip()
        if not requirements:
            requirements = self._last_requirements or ""
        if not requirements:
            raise ValueError(
                "requirements must not be empty; pass the original requirements "
                "or call analyze_software_requirements first"
            )
        if len(requirements) > 12_000:
            raise ValueError("requirements must not exceed 12000 characters")

        if not isinstance(model_provider, str) or not model_provider.strip():
            model_provider = settings.model_provider
        if not isinstance(model_provider, str) or not model_provider.strip():
            raise ValueError(
                "model_provider must not be empty and settings.model_provider "
                "must be configured"
            )

        analysis: RequirementAnalysis | None = None
        try:
            if isinstance(requirements_analysis_json, RequirementAnalysis):
                analysis = requirements_analysis_json
            elif isinstance(requirements_analysis_json, dict):
                analysis = RequirementAnalysis.model_validate(
                    requirements_analysis_json
                )
            elif requirements_analysis_json is None:
                analysis = None
            elif isinstance(requirements_analysis_json, str):
                analysis_text = requirements_analysis_json.strip()
                if analysis_text:
                    # Some model/tool handoffs JSON-encode a JSON string twice.
                    normalized: Any = json.loads(analysis_text)
                    if isinstance(normalized, str):
                        normalized = json.loads(normalized)
                    analysis = RequirementAnalysis.model_validate(normalized)
            else:
                raise TypeError(
                    "requirements_analysis_json must be a JSON string, object, "
                    "RequirementAnalysis, or null"
                )
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            logger.exception(
                "event=agent_delegation_input_validation_failed "
                "specialist=architecture_design "
                "field=requirements_analysis_json"
            )
            raise ValueError(
                "requirements_analysis_json is not a valid RequirementAnalysis"
            ) from exc

        try:
            response = await self._architecture_agent.design(
                requirements=requirements,
                model_provider=model_provider.strip().lower(),
                requirements_analysis=analysis,
            )
        except Exception:
            logger.exception(
                "event=agent_delegation_failed specialist=architecture_design"
            )
            raise

        # A new architecture must not inherit a prior review.
        response = response.model_copy(update={"review": None})
        self._last_architecture_response = response
        logger.info("event=agent_delegation_completed specialist=architecture_design")
        return response.model_dump_json()

    async def review_architecture(
        self,
        architecture_response_json: Any = "",
    ) -> str:
        """Review an architecture JSON document and return review JSON."""
        response: ArchitectureResponse | None = None
        parse_error: ValidationError | json.JSONDecodeError | TypeError | None = None

        if isinstance(architecture_response_json, ArchitectureResponse):
            response = architecture_response_json
        elif isinstance(architecture_response_json, dict):
            try:
                response = ArchitectureResponse.model_validate(
                    architecture_response_json
                )
            except ValidationError as exc:
                parse_error = exc
        elif isinstance(architecture_response_json, str):
            text = architecture_response_json.strip()
            if text.startswith("```"):
                text = text.strip("`").strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            if text:
                try:
                    normalized: Any = json.loads(text)
                    if isinstance(normalized, str):
                        normalized = json.loads(normalized)
                    response = ArchitectureResponse.model_validate(normalized)
                except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                    parse_error = exc  # type: ignore[assignment]

        if response is None and self._last_architecture_response is not None:
            logger.warning(
                "event=agent_delegation_json_recovery "
                "specialist=architecture_review "
                "reason=invalid_or_missing_architecture_json"
            )
            response = self._last_architecture_response

        if response is None:
            logger.exception(
                "event=agent_delegation_input_validation_failed "
                "specialist=architecture_review "
                "field=architecture_response_json"
            )
            raise ValueError(
                "architecture_response_json is not a valid ArchitectureResponse"
            ) from parse_error

        try:
            review = await self._architecture_review_agent.review(response)
        except Exception:
            logger.exception(
                "event=agent_delegation_failed specialist=architecture_review"
            )
            raise

        self._reviewed_responses[self._architecture_key(response)] = review
        logger.info("event=agent_delegation_completed specialist=architecture_review")
        return review.model_dump_json()

    def build_tools(self) -> list[Any]:
        """Return MAF FunctionTools with stable names and explicit input contracts."""

        @tool(
            name="analyze_software_requirements",
            description=(
                "Delegate requirements classification to the Requirements Analysis "
                "specialist. Returns a JSON RequirementAnalysis with functional and "
                "non-functional requirements, assumptions, open questions, and constraints."
            ),
            approval_mode="never_require",
        )
        async def analyze_software_requirements(
            requirements: Annotated[
                str,
                Field(description="The user's software requirements, up to 12000 characters."),
            ],
        ) -> str:
            return await self.analyze_requirements(requirements)

        @tool(
            name="design_software_architecture",
            description=(
                "Delegate architecture design to the Architecture specialist. Pass the "
                "original requirements, a model provider name, and optionally the JSON "
                "output from analyze_software_requirements. Returns ArchitectureResponse JSON."
            ),
            approval_mode="never_require",
        )
        async def design_software_architecture(
            requirements: Annotated[
                Any,
                Field(description="The user's software requirements, up to 12000 characters."),
            ] = "",
            model_provider: Annotated[
                Any,
                Field(description="Configured model provider, for example 'openai'."),
            ] = "",
            requirements_analysis_json: Annotated[
                Any,
                Field(description="Optional JSON output from analyze_software_requirements."),
            ] = "",
        ) -> str:
            return await self.design_architecture(
                requirements,
                model_provider,
                requirements_analysis_json,
            )

        @tool(
            name="review_software_architecture",
            description=(
                "Delegate architecture review to the Architecture Review specialist. "
                "Input must be the JSON output from design_software_architecture. "
                "Returns ArchitectureReview JSON with findings and a recommendation."
            ),
            approval_mode="never_require",
        )
        async def review_software_architecture(
            architecture_response_json: Annotated[
                Any,
                Field(
                    description=(
                        "Optional ArchitectureResponse JSON. When omitted or "
                        "malformed, the review tool uses the cached design."
                    )
                ),
            ] = "",
        ) -> str:
            return await self.review_architecture(architecture_response_json)

        return [
            analyze_software_requirements,
            design_software_architecture,
            review_software_architecture,
        ]
