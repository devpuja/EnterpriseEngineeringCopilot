
import asyncio
import json
from typing import cast

from unittest.mock import patch
from app.config.settings import settings

from app.services.mcp_client_service import validate_architecture_diagram


VALID_DIAGRAM = (
    'flowchart LR\n'
    '    client["Client"]\n'
    '    api["Application API"]\n'
    '    client --> api'
)

INVALID_DIAGRAM = "this is not a valid mermaid flowchart"


def parse_result(result: str) -> dict[str, object]:
    parsed: object = json.loads(result)

    if not isinstance(parsed, dict):
        raise AssertionError("Expected a JSON object from the MCP service.")

    return cast(dict[str, object], parsed)



class HangingMCPClient:
    """Fake MCP client that simulates a tool call that never completes."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def __aenter__(self) -> "HangingMCPClient":
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    async def call_tool(self, tool_name: str, arguments: dict[str, str]) -> object:
        await asyncio.Event().wait()


async def main() -> None:
    print("=== TEST 1: Valid diagram through MCP client service ===")

    valid_result = await validate_architecture_diagram(diagram=VALID_DIAGRAM)
    valid_payload = parse_result(valid_result)

    assert valid_payload.get("valid") is True, (
        f"Expected valid=True, got: {valid_payload}"
    )

    print("PASS: Valid diagram accepted.")

    print("\n=== TEST 2: Invalid diagram through MCP client service ===")

    invalid_result = await validate_architecture_diagram(diagram=INVALID_DIAGRAM)
    invalid_payload = parse_result(invalid_result)
    assert invalid_payload.get("valid") is False, (
        f"Expected valid=False, got: {invalid_payload}"
    )

    errors_value = invalid_payload.get("errors")
    assert isinstance(errors_value, list), (
        "Expected validation errors for the invalid diagram."
    )
    
    errors = cast(list[object], errors_value)
    assert len(errors) > 0, (
        "Expected validation errors for the invalid diagram."
    )

    print("PASS: Invalid diagram returned validation errors.")
    print("\nAll MCP client service checks passed.")



    print("\n=== TEST 3: MCP client execution timeout ===")

    original_timeout = settings.mcp_timeout_seconds
    settings.mcp_timeout_seconds = 0.1

    try:
        with patch(
            "app.services.mcp_client_service.Client",
            HangingMCPClient,
        ):
            try:
                await validate_architecture_diagram(diagram=VALID_DIAGRAM)
            except TimeoutError as exc:
                assert "configured timeout" in str(exc).lower(), (
                    "Expected a clear MCP timeout error message."
                )
                print("PASS: Stalled MCP call raised TimeoutError.")
            else:
                raise AssertionError(
                    "Expected the stalled MCP call to time out."
                )
    finally:
        settings.mcp_timeout_seconds = original_timeout



if __name__ == "__main__":
    asyncio.run(main())
