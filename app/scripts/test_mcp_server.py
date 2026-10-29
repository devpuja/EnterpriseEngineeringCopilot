
import asyncio
import json
from typing import TypeAlias, cast

from mcp import Client

from app.tools.diagram_validation import MAX_DIAGRAM_CHARS


JsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)

MCP_URL = "http://127.0.0.1:8001/mcp"
TOOL_NAME = "validate_architecture_diagram"


def print_result(result: object) -> None:
    """Print the MCP result for inspection."""
    print(result)


def parse_json_object(text: str) -> dict[str, JsonValue] | None:
    """Parse JSON and return a dictionary only when the root is an object."""
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    return cast(dict[str, JsonValue], parsed)


def extract_result_text(result: object) -> str:
    """Extract the result string from the MCP structured content."""
    # MCP result objects expose structured_content. Keep the runtime
    # checks explicit so unexpected response shapes fail safely.
    structured_content: object = getattr(result, "structured_content", None)

    if not isinstance(structured_content, dict):
        return ""

    structured_result = cast(dict[str, JsonValue], structured_content)
    result_value: object = structured_result.get("result", "")

    if isinstance(result_value, str):
        return result_value

    return ""


async def main() -> None:
    async with Client(MCP_URL) as client:

        # TEST 1: Invalid Mermaid diagram
        print("\n=== TEST 1: Invalid diagram ===")

        invalid_result = await client.call_tool(
            TOOL_NAME,
            {"diagram": "this is not a valid mermaid flowchart"},
        )

        print_result(invalid_result)

        assert not invalid_result.is_error, (
            "The tool execution failed instead of returning "
            "a controlled validation result."
        )

        result_text = extract_result_text(invalid_result)
        payload = parse_json_object(result_text)

        assert payload is not None, (
            "Expected the tool to return a JSON object."
        )

        valid_value = payload.get("valid")
        errors_value = payload.get("errors")

        assert valid_value is False, (
            "Expected the invalid diagram to be rejected."
        )
        assert isinstance(errors_value, list) and errors_value, (
            "Expected a non-empty list of validation errors."
        )
        assert all(isinstance(error, str) for error in errors_value), (
            "Expected validation errors to be strings."
        )

        print("PASS: Invalid diagram returned validation errors.")


        # TEST 2: Oversized diagram
        print("\n=== TEST 2: Oversized diagram ===")
        print(f"Maximum permitted characters: {MAX_DIAGRAM_CHARS}")

        oversized_diagram = "x" * (MAX_DIAGRAM_CHARS + 1)

        try:
            oversized_result = await client.call_tool(
                TOOL_NAME,
                {"diagram": oversized_diagram},
            )

            print_result(oversized_result)

            if oversized_result.is_error:
                print(
                    "PASS: MCP server rejected the oversized input "
                    "with a tool error."
                )
            else:
                oversized_text = extract_result_text(oversized_result)
                oversized_payload = parse_json_object(oversized_text)

                assert oversized_payload is not None, (
                    "Expected a structured response for oversized input."
                )

                oversized_errors_value = oversized_payload.get("errors")
                oversized_errors: list[str] = []

                if isinstance(oversized_errors_value, list):
                    oversized_errors = [
                        error
                        for error in oversized_errors_value
                        if isinstance(error, str)
                    ]

                error_text = " ".join(oversized_errors).lower()

                assert (
                    "maximum" in error_text
                    or "length" in error_text
                    or "too long" in error_text
                ), (
                    "The oversized input was not clearly rejected. "
                    "Inspect the actual result above."
                )

                print(
                    "PASS: Oversized input returned a length-related "
                    "validation error."
                )

        except Exception as exc:
            message = str(exc)
            message_lower = message.lower()

            print(
                f"Client/server rejected oversized input: "
                f"{type(exc).__name__}: {message}"
            )

            assert any(word in message_lower
                for word in ("maximum", "length", "too long", "validation")
            ), (
                "The exception did not clearly indicate an input-length "
                "rejection."
            )

            print("PASS: Oversized input was rejected.")
            
        
        
        # TEST 3: Empty diagram
        print("\n=== TEST 3: Empty diagram ===")

        try:
            empty_result = await client.call_tool(
                TOOL_NAME,
                {"diagram": ""},
            )
        except Exception as exc:
            message_lower = str(exc).lower()

            assert any(
                word in message_lower
                for word in (
                    "minimum",
                    "at least",
                    "min_length",
                    "validation",
                    "character",
                )
            ), (
                "Empty input was rejected, but the error did not "
                "clearly indicate an input-validation failure."
            )

            print("PASS: Empty input was rejected by input validation.")
        else:
            print_result(empty_result)

            assert empty_result.is_error, (
                "Expected the MCP server to reject an empty diagram."
            )

            print("PASS: Empty input was rejected by the MCP server.")
            
        
        
        # TEST 4: Whitespace-only diagram
        print("\n=== TEST 4: Whitespace-only diagram ===")

        whitespace_result = await client.call_tool(
            TOOL_NAME,
            {"diagram": "   \n\t   "},
        )

        print_result(whitespace_result)

        assert not whitespace_result.is_error, (
            "Whitespace-only input should return a controlled "
            "diagram-validation result."
        )

        whitespace_text = extract_result_text(whitespace_result)
        whitespace_payload = parse_json_object(whitespace_text)

        assert whitespace_payload is not None, (
            "Expected a JSON validation result for whitespace-only input."
        )

        assert whitespace_payload.get("valid") is False, (
            "Expected whitespace-only input to be marked invalid."
        )

        whitespace_errors = whitespace_payload.get("errors")

        assert isinstance(whitespace_errors, list), (
            "Expected validation errors to be returned as a list."
        )

        assert len(whitespace_errors) > 0, (
            "Expected whitespace-only input to return validation errors."
        )

        for error in whitespace_errors:
            assert isinstance(error, str), (
                "Expected each validation error to be a string."
            )

        print("PASS: Whitespace-only input returned controlled validation errors.")




if __name__ == "__main__":
    asyncio.run(main())
