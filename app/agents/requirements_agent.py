
import json
import logging
import re
from typing import Any, cast

from agent_framework import Agent
from pydantic import ValidationError

from app.api.schemas import RequirementAnalysis
from app.services.model_client import create_model_client

logger = logging.getLogger(__name__)


REQUIREMENTS_ANALYSIS_INSTRUCTIONS = """
You are the Requirements Analysis Agent in an enterprise software
architecture engineering system.

Your responsibility is to analyze the user's software requirements.
Do not design the architecture or select technologies.

Extract and classify information into these fields:

1. functional_requirements:
   What the system must do or what capabilities it must provide.

2. non_functional_requirements:
   Quality attributes such as security, performance, scalability,
   availability, reliability, maintainability, and observability.
   Include only requirements supported by the input. Do not invent
   numerical targets.

3. assumptions:
   Reasonable assumptions needed to interpret incomplete requirements.
   Clearly distinguish assumptions from facts stated by the user.

4. open_questions:
   Important unanswered questions that could materially affect
   architecture, implementation, security, cost, or operations.
   Do not ask questions whose answers are already provided.

5. constraints:
   Explicit restrictions or boundaries, such as required cloud provider,
   programming language, existing systems, budget, deadlines, regulatory
   obligations, or mandated technologies.
   Do not invent constraints.

Rules:
- Preserve the user's intent.
- Do not invent requirements, facts, budgets, metrics, or compliance needs.
- Keep each item concise, specific, and independently understandable.
- Avoid duplicate items across categories.
- If information is missing, use assumptions and open_questions
  appropriately instead of presenting guesses as facts.
- Return a structured response matching the requested schema.
"""


class RequirementsAnalysisAgent:
    """Analyzes software requirements using Microsoft Agent Framework."""

    def __init__(self, agent: Any | None = None) -> None:
        # Dependency injection allows unit tests to use a fake agent
        # without making real model calls.
        self._agent = (
            agent
            if agent is not None
            else Agent(
                client=cast(Any, create_model_client()),
                name="RequirementsAnalysisAgent",
                instructions=REQUIREMENTS_ANALYSIS_INSTRUCTIONS,
            )
        )

    async def analyze(self, requirements: str) -> RequirementAnalysis:
        """Convert a requirements description into a validated analysis."""

        if not requirements or not requirements.strip():
            raise ValueError("Requirements must not be empty.")

        prompt = (
            "Analyze the following software requirements.\n\n"
            "<requirements>\n"
            f"{requirements.strip()}\n"
            "</requirements>\n\n"
            "Return the result using the required structured schema."
        )

        try:
            result = await self._agent.run(
                prompt,
                options={"response_format": RequirementAnalysis},
            )

            value = getattr(result, "value", None)

            if isinstance(value, RequirementAnalysis):
                return value

            if isinstance(value, dict):
                return RequirementAnalysis.model_validate(value)

            # Fallback for providers or responses that expose JSON as text.
            response_text = getattr(result, "text", None)

            if not isinstance(response_text, str) or not response_text.strip():
                raise ValueError(
                    "The model returned no structured requirements analysis."
                )

            cleaned_text = response_text.strip()
            cleaned_text = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                cleaned_text,
                flags=re.IGNORECASE,
            ).strip()

            payload = json.loads(cleaned_text)
            return RequirementAnalysis.model_validate(payload)

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "Requirements analysis returned invalid structured output: %s",
                exc,
            )
            raise ValueError(
                "The model returned an invalid requirements analysis."
            ) from exc