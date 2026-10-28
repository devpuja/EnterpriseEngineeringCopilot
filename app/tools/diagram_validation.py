"""Typed, read-only tool contract for validating Mermaid architecture diagrams."""

import json
from typing import Annotated, Any

from pydantic import Field

from app.services.diagram_validator import validate_mermaid_flowchart

MAX_DIAGRAM_CHARS = 20_000


def validate_architecture_diagram(
    diagram: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_DIAGRAM_CHARS,
            description=(
                "Mermaid architecture diagram source to validate. Provide the raw "
                "diagram text without Markdown code fences."
            ),
        ),
    ],
) -> str:
    """Validate a Mermaid architecture diagram and return a JSON result.

    This tool is read-only: it validates supplied text using the application's
    deterministic validator and does not access files, networks, or external systems.
    The returned JSON shape is stable so it can be consumed by an agent or a test.
    """
    normalized_diagram = diagram.strip()
    if not normalized_diagram:
        return _result_json(valid=False, errors=["Diagram is empty."])

    if len(diagram) > MAX_DIAGRAM_CHARS:
        return _result_json(
            valid=False,
            errors=[
                f"Diagram exceeds the maximum allowed length of {MAX_DIAGRAM_CHARS} characters."
            ],
        )

    errors = validate_mermaid_flowchart(normalized_diagram)
    return _result_json(valid=not errors, errors=errors)


def _result_json(*, valid: bool, errors: list[str]) -> str:
    """Serialize tool output consistently for model tool-call handling."""
    payload: dict[str, Any] = {"valid": valid, "errors": errors}
    return json.dumps(payload, ensure_ascii=False)
