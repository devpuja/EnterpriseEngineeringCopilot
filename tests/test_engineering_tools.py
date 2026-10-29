
"""Tests for safe engineering-tool API error handling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api import engineering_tools
from app.api.schemas import DiagramToolRequest, DiagramToolResponse


VALID_DIAGRAM = (
    'flowchart LR\n'
    '    client["Client"]\n'
    '    api["Application API"]\n'
    '    client --> api'
)


def test_timeout_returns_safe_504_response() -> None:
    with patch.object(
        engineering_tools.diagram_tool_agent,
        "review_diagram",
        new_callable=AsyncMock,
        side_effect=TimeoutError("internal timeout details"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                engineering_tools.review_diagram(
                    DiagramToolRequest(diagram=VALID_DIAGRAM)
                )
            )

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == (
        "Diagram validation timed out. Please try again."
    )
    assert "internal timeout details" not in str(exc_info.value.detail)


def test_unexpected_error_returns_safe_502_response() -> None:
    with patch.object(
        engineering_tools.diagram_tool_agent,
        "review_diagram",
        new_callable=AsyncMock,
        side_effect=RuntimeError("sensitive internal details"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                engineering_tools.review_diagram(
                    DiagramToolRequest(diagram=VALID_DIAGRAM)
                )
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == (
        "Diagram validation failed. Check application logs."
    )
    assert "sensitive internal details" not in str(exc_info.value.detail)


def test_successful_validation_response_is_unchanged() -> None:
    expected_answer = (
        "Validation result: valid\n\n"
        "Errors returned by the validator: none"
    )

    with patch.object(
        engineering_tools.diagram_tool_agent,
        "review_diagram",
        new_callable=AsyncMock,
        return_value=expected_answer,
    ):
        response = asyncio.run(
            engineering_tools.review_diagram(
                DiagramToolRequest(diagram=VALID_DIAGRAM)
            )
        )

    assert isinstance(response, DiagramToolResponse)
    assert response.answer == expected_answer