
"""MCP server exposing selected engineering capabilities."""

from typing import Annotated
from app.observability.telemetry import observed

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
@observed("tool.validate_diagram")
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
    import uvicorn
    from app.config.settings import settings
    from app.observability.logging import configure_logging
    from app.observability.telemetry import configure_telemetry, shutdown_telemetry
    from app.observability.middleware import RequestContextMiddleware

    configure_logging(settings.log_level, settings.log_format)
    configure_telemetry()
    application = mcp_server.streamable_http_app(stateless_http=True)
    application.add_middleware(RequestContextMiddleware)
    try:
        uvicorn.run(application, host="127.0.0.1", port=8001)
    finally:
        shutdown_telemetry()
