
"""MCP client service for invoking engineering tools."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from app.observability.telemetry import observed
import ipaddress
import json
import logging
from typing import Annotated
from urllib.parse import urlparse
from mcp import Client
from pydantic import Field

from app.config.settings import settings
from app.tools.diagram_validation import MAX_DIAGRAM_CHARS

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _connect_client() -> AsyncIterator[Client]:
    if not settings.telemetry_enabled:
        async with Client(settings.mcp_server_url) as client:
            yield client
        return
    import httpx2
    from mcp.client.streamable_http import streamable_http_client
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    headers: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(headers)
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with Client(streamable_http_client(
            settings.mcp_server_url, http_client=http_client,
        )) as client:
            yield client

ALLOWED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "validate_architecture_diagram",
    }
)

# True means explicit approval is required before execution.
# Every allowlisted tool must have an entry.
TOOL_APPROVAL_REQUIRED: dict[str, bool] = {
    "validate_architecture_diagram": False,
}

TOOL_RISK_LEVELS: dict[str, str] = {
    "validate_architecture_diagram": "low",
}

def ensure_tool_execution_allowed(tool_name: str, *, approved: bool = False) -> None:
    """Enforce tool allowlisting and the configured approval policy."""
    if tool_name not in ALLOWED_MCP_TOOLS:
        raise ValueError(f"MCP tool '{tool_name}' is not allowed.")

    risk_level = TOOL_RISK_LEVELS.get(tool_name)
    if risk_level not in {"low", "medium", "high"}:
        raise ValueError(
            f"No risk classification is configured for MCP tool '{tool_name}'."
        )

    approval_required = TOOL_APPROVAL_REQUIRED.get(tool_name)

    if approval_required is None:
        raise ValueError(
            f"No approval policy is configured for MCP tool '{tool_name}'."
        )

    if approval_required and not approved:
        raise PermissionError(
            f"MCP tool '{tool_name}' requires explicit approval."
        )
    if risk_level == "high" and not approval_required:
        raise ValueError(
            f"High-risk MCP tool '{tool_name}' must require explicit approval."
        )


def _validate_mcp_server_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MCP server must use a loopback HTTP endpoint.")
    if parsed.hostname.lower() == "localhost":
        return
    try:
        if ipaddress.ip_address(parsed.hostname).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("MCP server must use a loopback HTTP endpoint.")


@observed("mcp.validate_diagram")
async def validate_architecture_diagram(
    diagram: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_DIAGRAM_CHARS,
            description=(
                "Raw Mermaid architecture diagram source. "
                "Do not include Markdown code fences."
            ),
        ),
    ],
) -> str:
    """Invoke the allowlisted diagram-validation tool through MCP."""
    tool_name = "validate_architecture_diagram"
    ensure_tool_execution_allowed(tool_name)
    if not isinstance(diagram, str) or not diagram.strip() or len(diagram) > MAX_DIAGRAM_CHARS:
        raise ValueError("Diagram input is invalid.")
    _validate_mcp_server_url(settings.mcp_server_url)

    try:
        async with asyncio.timeout(settings.mcp_timeout_seconds):
            async with _connect_client() as client:
                result = await client.call_tool(
                    tool_name,
                    {"diagram": diagram},
                )
    except TimeoutError as exc:
        raise TimeoutError(
            "The MCP tool call exceeded the configured timeout "
            f"of {settings.mcp_timeout_seconds:g} seconds."
        ) from exc

    if result.is_error:
        logger.warning("event=mcp_tool_failed tool=%s", tool_name)
        raise RuntimeError(
            "The MCP server could not execute the diagram validation tool."
        )

    for content_item in result.content:
        content_text: object = getattr(content_item, "text", None)

        if isinstance(content_text, str) and content_text:
            if len(content_text) > MAX_DIAGRAM_CHARS:
                raise RuntimeError("The MCP tool returned an oversized result.")
            try:
                payload = json.loads(content_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError("The MCP tool returned an invalid result.") from exc
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("valid"), bool)
                or not isinstance(payload.get("errors"), list)
                or any(not isinstance(error, str) for error in payload["errors"])
            ):
                raise RuntimeError("The MCP tool returned an invalid result.")
            logger.info("event=mcp_tool_completed tool=%s", tool_name)
            return json.dumps(
                {"valid": payload["valid"], "errors": payload["errors"]},
                ensure_ascii=False,
            )

    raise RuntimeError(
        "The MCP server returned no usable diagram validation result."
    )
