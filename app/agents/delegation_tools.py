"""Explicit, schema-described delegation tools for specialist agents.

These wrappers let a parent Microsoft Agent Framework agent invoke the
existing requirements, architecture-design, and architecture-review agents
as tools. They do not replace the current workflow orchestrator.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import uuid4

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


@dataclass(frozen=True)
class ArchitectureResultEntry:
    architecture: ArchitectureResponse
    created_at: float
    review: ArchitectureReview | None = None


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
        self._last_requirements: str | None = None
        self._architecture_results: dict[str, ArchitectureResultEntry] = {}
        self._retention_seconds = 30 * 60
        self._max_entries = 100
        self._review_invocation_count = 0
        self._last_architecture_id: str | None = None
        self._reviewed_architecture_id: str | None = None
        self._requirements_results: dict[str, tuple[RequirementAnalysis, float]] = {}

    @staticmethod
    def _architecture_key(response: ArchitectureResponse) -> str:
        return response.model_copy(update={"review": None}).model_dump_json()

    def attach_review(self, response: ArchitectureResponse) -> ArchitectureResponse:
        """Attach a review captured by the review specialist, when available."""
        for entry in reversed(list(self._architecture_results.values())):
            if entry.architecture == response.model_copy(update={"review": None}):
                if entry.review is not None:
                    return response.model_copy(update={"review": entry.review})
        return response

    def _cleanup_result_store(self) -> None:
        now = time.monotonic()
        expired_ids = [
            architecture_id
            for architecture_id, entry in self._architecture_results.items()
            if now - entry.created_at > self._retention_seconds
        ]
        for architecture_id in expired_ids:
            del self._architecture_results[architecture_id]

        while len(self._architecture_results) > self._max_entries:
            oldest_id = min(
                self._architecture_results,
                key=lambda item: self._architecture_results[item].created_at,
            )
            del self._architecture_results[oldest_id]

    def get_architecture(self, architecture_id: str) -> ArchitectureResponse:
        self._cleanup_result_store()
        entry = self._architecture_results.get(architecture_id)
        if entry is None:
            raise ValueError(
                f"Unknown or expired architecture_id: {architecture_id}"
            )
        return entry.architecture

    def get_requirements_analysis(
        self,
        requirements_id: str,
    ) -> RequirementAnalysis:
        entry = self._requirements_results.get(requirements_id)
        if entry is None:
            raise ValueError(
                f"Unknown or expired requirements_id: {requirements_id}"
            )
        analysis, created_at = entry
        if time.monotonic() - created_at > self._retention_seconds:
            del self._requirements_results[requirements_id]
            raise ValueError(
                f"Unknown or expired requirements_id: {requirements_id}"
            )
        return analysis

    def get_verified_review(
        self,
        architecture_id: str,
    ) -> ArchitectureReview:
        self._cleanup_result_store()
        entry = self._architecture_results.get(architecture_id)
        if entry is None:
            raise RuntimeError(
                f"Unknown or expired architecture_id: {architecture_id}"
            )
        if entry.review is None:
            raise RuntimeError(
                "Architecture review was not completed for architecture_id "
                f"{architecture_id}"
            )
        return entry.review

    def get_verified_architecture_response(self) -> ArchitectureResponse:
        self._cleanup_result_store()
        architecture_id = self._reviewed_architecture_id
        if architecture_id is None or architecture_id != self._last_architecture_id:
            raise RuntimeError(
                "Delegated workflow does not contain a genuine review for "
                "the latest architecture."
            )
        entry = self._architecture_results.get(architecture_id)
        if entry is None or entry.review is None:
            raise RuntimeError(
                "Unknown architecture review state; the review may be missing "
                "or expired."
            )
        architecture = entry.architecture.model_copy(
            update={"review": entry.review}
        )
        logger.info(
            "event=delegated_review_verified "
            "architecture_id=%s review_status=completed findings=%d",
            architecture_id,
            len(entry.review.findings),
        )
        return architecture

    async def analyze_requirements(self, requirements: str) -> str:
        """Analyze requirements and return validated RequirementAnalysis JSON."""
        started_at = time.perf_counter()
        if not requirements or not requirements.strip():
            raise ValueError("requirements must not be empty")
        if len(requirements) > 12_000:
            raise ValueError("requirements must not exceed 12000 characters")

        try:
            analysis = await self._requirements_agent.analyze(requirements.strip())
        except Exception:
            logger.exception(
                "event=agent_delegation_failed specialist=requirements_analysis "
                "duration_ms=%.2f",
                round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise

        self._last_requirements = requirements.strip()
        requirements_id = str(uuid4())
        now = time.monotonic()
        self._requirements_results[requirements_id] = (analysis, now)
        expired_ids = [
            item_id
            for item_id, (_, created_at) in self._requirements_results.items()
            if now - created_at > self._retention_seconds
        ]
        for item_id in expired_ids:
            del self._requirements_results[item_id]
        logger.info(
            "event=agent_delegation_completed specialist=requirements_analysis "
            "requirements_id=%s duration_ms=%.2f",
            requirements_id,
            round((time.perf_counter() - started_at) * 1000, 2),
        )
        return json.dumps({
            "requirements_id": requirements_id,
            "functional_requirement_count": len(
                analysis.functional_requirements
            ),
            "next_step": "design_software_architecture",
        })

    async def design_architecture(
        self,
        requirements: Any = "",
        model_provider: Any = "",
        requirements_analysis_json: Any = "",
        requirements_id: Any = "",
    ) -> str:
        """Design architecture, optionally using JSON from requirements analysis."""
        started_at = time.perf_counter()
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
            if isinstance(requirements_id, str) and requirements_id.strip():
                analysis = self.get_requirements_analysis(
                    requirements_id.strip()
                )
            elif isinstance(requirements_analysis_json, RequirementAnalysis):
                analysis = requirements_analysis_json
            elif isinstance(requirements_analysis_json, dict):
                if "requirements_id" in requirements_analysis_json:
                    analysis = self.get_requirements_analysis(
                        str(requirements_analysis_json["requirements_id"])
                    )
                else:
                    # Backward compatibility for old/direct callers only.
                    analysis = RequirementAnalysis.model_validate(
                        requirements_analysis_json
                    )
            elif requirements_analysis_json is None:
                analysis = None
            elif isinstance(requirements_analysis_json, str):
                analysis_text = requirements_analysis_json.strip()
                if analysis_text:
                    normalized: Any = json.loads(analysis_text)
                    if isinstance(normalized, str):
                        normalized = json.loads(normalized)
                    if isinstance(normalized, dict) and "requirements_id" in normalized:
                        analysis = self.get_requirements_analysis(
                            str(normalized["requirements_id"])
                        )
                    else:
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
                "event=agent_delegation_failed specialist=architecture_design "
                "duration_ms=%.2f",
                round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise

        # A new architecture must not inherit a prior review.
        response = response.model_copy(update={"review": None})
        self._cleanup_result_store()
        architecture_id = str(uuid4())
        self._architecture_results[architecture_id] = ArchitectureResultEntry(
            architecture=response,
            created_at=time.monotonic(),
        )
        self._last_architecture_id = architecture_id
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "event=agent_delegation_completed specialist=architecture_design "
            "architecture_id=%s duration_ms=%.2f",
            architecture_id,
            duration_ms,
        )
        return json.dumps({
            "architecture_id": architecture_id,
            "summary": response.architecture.summary,
            "next_step": "review_software_architecture",
        })

    async def review_architecture(
        self,
        architecture_id: Any = "",
    ) -> str:
        """Review the architecture stored under an architecture ID."""
        if not isinstance(architecture_id, str) or not architecture_id.strip():
            raise ValueError("architecture_id is required")

        architecture_id = architecture_id.strip()
        started_at = time.perf_counter()
        logger.info(
            "event=agent_delegation_started specialist=architecture_review "
            "architecture_id=%s",
            architecture_id,
        )
        response = self.get_architecture(architecture_id)

        try:
            review = await self._architecture_review_agent.review(response)
        except Exception:
            logger.exception(
                "event=agent_delegation_failed specialist=architecture_review "
                "architecture_id=%s duration_ms=%.2f",
                architecture_id,
                round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise

        if not isinstance(review, ArchitectureReview):
            raise RuntimeError(
                "Architecture Review specialist returned an invalid "
                "ArchitectureReview."
            )

        entry = self._architecture_results[architecture_id]
        self._architecture_results[architecture_id] = ArchitectureResultEntry(
            architecture=entry.architecture,
            created_at=entry.created_at,
            review=review,
        )
        self._reviewed_architecture_id = architecture_id
        self._review_invocation_count += 1
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "event=agent_delegation_completed specialist=architecture_review "
            "architecture_id=%s findings=%d recommendation=%s "
            "duration_ms=%.2f",
            architecture_id,
            len(review.findings),
            review.approval_recommendation,
            duration_ms,
        )
        return review.model_dump_json()

    def build_tools(self) -> list[Any]:
        """Return MAF FunctionTools with stable names and explicit input contracts."""

        @tool(
            name="analyze_software_requirements",
            description=(
                "Delegate requirements classification to the Requirements Analysis "
                "specialist. Returns a compact requirements_id envelope. Use that ID "
                "when calling design_software_architecture."
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
                "output or requirements_id from analyze_software_requirements. Returns a compact JSON "
                "object containing architecture_id, summary, and next_step."
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
            requirements_id: Annotated[
                Any,
                Field(description="Optional requirements_id returned by analyze_software_requirements."),
            ] = "",
        ) -> str:
            return await self.design_architecture(
                requirements,
                model_provider,
                requirements_analysis_json,
                requirements_id,
            )

        @tool(
            name="review_software_architecture",
            description=(
                "Delegate architecture review to the Architecture Review specialist. "
                "Pass only the architecture_id returned by design_software_architecture. "
                "Never pass or reconstruct the architecture JSON. Returns the validated "
                "ArchitectureReview with findings and a recommendation."
            ),
            approval_mode="never_require",
        )
        async def review_software_architecture(
            architecture_id: Annotated[
                str,
                Field(
                    description=(
                        "The architecture_id returned by "
                        "design_software_architecture."
                    )
                ),
            ],
        ) -> str:
            return await self.review_architecture(architecture_id)

        return [
            analyze_software_requirements,
            design_software_architecture,
            review_software_architecture,
        ]
