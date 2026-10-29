
"""MCP client service for invoking engineering tools."""

from typing import Annotated

from mcp import Client
from pydantic import Field

from app.config.settings import settings
from app.tools.diagram_validation import MAX_DIAGRAM_CHARS


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
    
    """Invoke the diagram validation tool through the MCP server."""
    async with Client(settings.mcp_server_url) as client:
        result = await client.call_tool(
            "validate_architecture_diagram",
            {"diagram": diagram},
        )

    if result.is_error:
        raise RuntimeError("The MCP server could not execute the diagram validation tool.")

    # Read the textual MCP response directly.
    for content_item in result.content:
        content_text: object = getattr(content_item, "text", None)

        if isinstance(content_text, str) and content_text:
            return content_text

    raise RuntimeError("The MCP server returned no usable diagram validation result.")
