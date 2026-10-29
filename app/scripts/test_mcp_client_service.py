
import asyncio
import json
from typing import cast

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


async def main() -> None:
    print("=== TEST 1: Valid diagram through MCP client service ===")

    valid_result = await validate_architecture_diagram(VALID_DIAGRAM)
    valid_payload = parse_result(valid_result)

    assert valid_payload.get("valid") is True, (
        f"Expected valid=True, got: {valid_payload}"
    )

    print("PASS: Valid diagram accepted.")

    print("\n=== TEST 2: Invalid diagram through MCP client service ===")

    invalid_result = await validate_architecture_diagram(INVALID_DIAGRAM)
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


if __name__ == "__main__":
    asyncio.run(main())
