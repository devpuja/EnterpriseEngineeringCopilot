
from app.services.diagram_validator import validate_mermaid_flowchart


def test_valid_flowchart_passes() -> None:
    diagram = (
        "flowchart LR\n"
        'client["Tenant / Client"] --> api["API Gateway"]\n'
        'api --> queue["Message Queue"]\n'
        'queue --> worker["Processing Worker"]'
    )

    assert validate_mermaid_flowchart(diagram) == []


def test_markdown_fences_are_rejected() -> None:
    diagram = (
        "```mermaid\n"
        "flowchart LR\n"
        "a[Client] --> b[API]\n"
        "```"
    )

    errors = validate_mermaid_flowchart(diagram)

    assert any("Markdown fences" in error for error in errors)


def test_sequence_diagram_syntax_is_rejected() -> None:
    diagram = (
        "sequenceDiagram\n"
        "participant A\n"
        "A->>B: Request"
    )

    errors = validate_mermaid_flowchart(diagram)

    assert len(errors) >= 1


def test_diagram_without_edges_is_rejected() -> None:
    diagram = 'flowchart LR\nclient["Tenant"]'

    errors = validate_mermaid_flowchart(diagram)

    assert any("edge" in error.lower() for error in errors)


def test_undeclared_target_is_rejected() -> None:
    diagram = (
        "flowchart LR\n"
        'client["Tenant"] --> api'
    )

    errors = validate_mermaid_flowchart(diagram)

    assert any("not declared" in error for error in errors)