
"""MCP server exposing selected engineering capabilities."""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from app.tools.diagram_validation import (
    MAX_DIAGRAM_CHARS,
    validate_architecture_diagram as validate_diagram_contract,
)

# How to test this server:
# 1. Start the server: python -m app.mcp_server
# 2. Run the test script: python -m app.scripts.test_mcp_server

mcp_server = MCPServer("Enterprise Engineering Copilot")


@mcp_server.tool()
def validate_architecture_diagram(
    diagram: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_DIAGRAM_CHARS,
            description=(
                "Raw Mermaid flowchart source to validate. "
                "Do not include Markdown code fences."
            ),
        ),
    ],
) -> str:
    """Validate a Mermaid architecture diagram using deterministic rules."""
    return validate_diagram_contract(diagram)


if __name__ == "__main__":
    mcp_server.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
    )
