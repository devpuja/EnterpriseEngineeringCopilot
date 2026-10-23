
import json
import logging
from typing import Any, cast

from pydantic import ValidationError
from agent_framework import Agent

from app.api.schemas import (
    ArchitectureResponse,
    ArchitectureReview,
)

from app.services.architecture_review_checks import (run_deterministic_architecture_checks)
from app.services.model_client import create_model_client
from app.services.review_finding_merge import merge_review_findings

logger = logging.getLogger(__name__)


ARCHITECTURE_REVIEW_INSTRUCTIONS = """
You are an enterprise software architecture reviewer.

Review the supplied architecture against its requirements.

Inspect:
- Security, authorization, tenant isolation, and data protection.
- Reliability, retries, idempotency, failure handling, and recovery.
- Consistency between requirements, components, data flow, and diagram.
- Scalability, maintainability, and cost risks.
- Missing components or unclear responsibilities.

Rules:
1. Return only findings supported by evidence in the supplied input.
2. Do not invent technologies, requirements, or implementation details.
3. Distinguish a confirmed omission from an area that is merely unclear.
4. Make recommendations specific and actionable.
5. Do not redesign the entire architecture.
6. If there are no material issues, return an empty findings list and
   recommend approval.
7. Use "revise" when material corrections are needed.
8. Use "needs_human_review" when a consequential decision cannot be
   resolved from the available information.
9. Use the required structured output schema.
10. Do not repeat the same underlying issue in multiple findings.
11. Use concise, grammatically correct finding titles.
12. Distinguish missing design evidence from proof that a control is absent.
13. Do not claim that a database persists processing results unless the
    input explicitly describes storing those results.
14. Do not treat encryption alone as proof of tenant isolation.
15. Return one finding per distinct underlying issue.
"""


class ArchitectureReviewAgent:
    def __init__(self, agent: Any | None = None) -> None:
        self._agent = (
            agent
            if agent is not None
            else Agent(
                client=cast(Any, create_model_client()),
                name="ArchitectureReviewAgent",
                instructions=ARCHITECTURE_REVIEW_INSTRUCTIONS,
            )
        )

    @staticmethod
    def _parse_review(result: Any) -> ArchitectureReview:
        value = getattr(result, "value", None)

        if isinstance(value, ArchitectureReview):
            return value

        if isinstance(value, dict):
            return ArchitectureReview.model_validate(value)

        text = getattr(result, "text", None)

        if not text and isinstance(value, str):
            text = value

        if not text:
            raise ValueError(
                "ArchitectureReviewAgent returned no structured review."
            )

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "ArchitectureReviewAgent returned invalid JSON."
            ) from exc

        try:
            return ArchitectureReview.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                "ArchitectureReviewAgent returned an invalid review schema."
            ) from exc
            

    async def review(self, response: ArchitectureResponse) -> ArchitectureReview:
        logger.info("event=architecture_review_started")

        deterministic_findings = (run_deterministic_architecture_checks(response))

        prompt = (
            "Review this architecture response. "
            "Return a structured ArchitectureReview.\n\n"
            "Architecture response:\n"
            f"{response.model_dump_json(indent=2)}"
        )

        result = await self._agent.run(
            prompt,
            options={"response_format": ArchitectureReview},
        )

        review = self._parse_review(result)

        # Merge rule-based findings with the model's findings.
        # Deduplicate exact matches without discarding findings that
        # have different evidence or recommendations.
        # merged: list[Any] = []
        # seen: set[tuple[Any, ...]] = set()

        # for finding in [*review.findings, *deterministic_findings]:
        #     key = (
        #         finding.severity,
        #         finding.category,
        #         finding.finding,
        #         finding.evidence,
        #         finding.recommendation,
        #     )

        #     if key not in seen:
        #         seen.add(key)
        #         merged.append(finding)

        merged = merge_review_findings(
            [*review.findings, *deterministic_findings]
        )
        
        recommendation = review.approval_recommendation

        # A deterministic high/critical finding must not be overridden
        # by an LLM approval.
                # Deterministic high/critical findings must not be overridden
        # by an LLM approval.
        if any(
            finding.severity in ("critical", "high")
            for finding in merged
        ):
            recommendation = "revise"
        elif merged and recommendation == "approve":
            recommendation = "revise"

        final_review = ArchitectureReview(
            summary=review.summary,
            findings=merged,
            approval_recommendation=recommendation,
        )

        logger.info(
            "event=architecture_review_completed findings=%d recommendation=%s",
            len(final_review.findings),
            final_review.approval_recommendation,
        )

        return final_review