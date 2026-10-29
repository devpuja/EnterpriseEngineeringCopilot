
"""MCP client service for invoking engineering tools."""

from typing import Annotated

from mcp import Client
from pydantic import Field

from app.config.settings import settings
from app.tools.diagram_validation import MAX_DIAGRAM_CHARS


ALLOWED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "validate_architecture_diagram",
    }
)


def _ensure_allowed_tool(tool_name: str) -> None:
    """Reject MCP tools that are not explicitly allowlisted."""
    if tool_name not in ALLOWED_MCP_TOOLS:
        raise ValueError(f"MCP tool '{tool_name}' is not allowed.")


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
    _ensure_allowed_tool(tool_name)

    async with Client(settings.mcp_server_url) as client:
        result = await client.call_tool(
            tool_name,
            {"diagram": diagram},
        )

    if result.is_error:
        raise RuntimeError(
            "The MCP server could not execute the diagram validation tool."
        )

    for content_item in result.content:
        content_text: object = getattr(content_item, "text", None)

        if isinstance(content_text, str) and content_text:
            return content_text

    raise RuntimeError(
        "The MCP server returned no usable diagram validation result."
    )