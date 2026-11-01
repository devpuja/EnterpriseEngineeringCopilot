
"""Tests for the MCP tool approval policy."""

import pytest

from app.services import mcp_client_service


def test_read_only_diagram_tool_does_not_require_approval() -> None:
    mcp_client_service.ensure_tool_execution_allowed(
        "validate_architecture_diagram"
    )


def test_unallowlisted_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="is not allowed"):
        mcp_client_service.ensure_tool_execution_allowed(
            "delete_repository"
        )


def test_tool_without_approval_policy_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_service,
        "ALLOWED_MCP_TOOLS",
        frozenset({"example_write_tool"}),
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_APPROVAL_REQUIRED",
        {},
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_RISK_LEVELS",
        {"example_write_tool": "low"},
    )

    with pytest.raises(ValueError, match="No approval policy"):
        mcp_client_service.ensure_tool_execution_allowed(
            "example_write_tool"
        )


def test_tool_requiring_approval_is_rejected_without_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_service,
        "ALLOWED_MCP_TOOLS",
        frozenset({"example_write_tool"}),
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_APPROVAL_REQUIRED",
        {"example_write_tool": True},
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_RISK_LEVELS",
        {"example_write_tool": "high"},
    )

    with pytest.raises(PermissionError, match="requires explicit approval"):
        mcp_client_service.ensure_tool_execution_allowed(
            "example_write_tool"
        )


def test_approved_tool_passes_policy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_service,
        "ALLOWED_MCP_TOOLS",
        frozenset({"example_write_tool"}),
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_APPROVAL_REQUIRED",
        {"example_write_tool": True},
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_RISK_LEVELS",
        {"example_write_tool": "high"},
    )

    mcp_client_service.ensure_tool_execution_allowed(
        "example_write_tool",
        approved=True,
    )


def test_high_risk_tool_cannot_be_configured_without_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_service,
        "ALLOWED_MCP_TOOLS",
        frozenset({"example_write_tool"}),
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_APPROVAL_REQUIRED",
        {"example_write_tool": False},
    )
    monkeypatch.setattr(
        mcp_client_service,
        "TOOL_RISK_LEVELS",
        {"example_write_tool": "high"},
    )

    with pytest.raises(ValueError, match="must require explicit approval"):
        mcp_client_service.ensure_tool_execution_allowed("example_write_tool")
