"""Unit tests for the deterministic contract behind the MAF diagram tool."""

import json
from typing import cast

import pytest
from pydantic import ValidationError

from app.api.schemas import DiagramToolRequest
from app.tools.diagram_validation import (
    MAX_DIAGRAM_CHARS,
    validate_architecture_diagram,
)

VALID_DIAGRAM = '''flowchart LR
    client["Client"]
    api["Application API"]
    client --> api'''


def parse_tool_result(result: str) -> dict[str, object]:
    payload = json.loads(result)
    assert isinstance(payload, dict)
    payload = cast(dict[str, object], payload)
    assert set(payload) == {"valid", "errors"}
    assert isinstance(payload["valid"], bool)
    assert isinstance(payload["errors"], list)
    return payload


def test_valid_diagram_returns_valid_result() -> None:
    payload = parse_tool_result(validate_architecture_diagram(VALID_DIAGRAM))
    assert payload == {"valid": True, "errors": []}


def test_undeclared_node_returns_validation_error() -> None:
    diagram = 'flowchart LR\n    client["Client"]\n    client --> missing'
    payload = parse_tool_result(validate_architecture_diagram(diagram))
    assert payload["valid"] is False
    errors = payload["errors"]
    assert isinstance(errors, list)
    errors = cast(list[str], errors)
    assert any("not declared explicitly" in error for error in errors)


def test_empty_diagram_returns_controlled_error() -> None:
    payload = parse_tool_result(validate_architecture_diagram("   \n "))
    assert payload == {"valid": False, "errors": ["Diagram is empty."]}


def test_oversized_diagram_returns_controlled_error() -> None:
    payload = parse_tool_result(
        validate_architecture_diagram("x" * (MAX_DIAGRAM_CHARS + 1))
    )
    assert payload["valid"] is False
    errors = payload["errors"]
    assert isinstance(errors, list)
    errors = cast(list[str], errors)
    assert any("maximum allowed length" in error for error in errors)


def test_request_schema_rejects_empty_diagram() -> None:
    with pytest.raises(ValidationError):
        DiagramToolRequest(diagram="")


def test_request_schema_rejects_oversized_diagram() -> None:
    with pytest.raises(ValidationError):
        DiagramToolRequest(diagram="x" * (MAX_DIAGRAM_CHARS + 1))
