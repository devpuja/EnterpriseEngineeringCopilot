
import re


NODE_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
EDGE_PATTERN = re.compile(r"-\.->|-->")


def validate_mermaid_flowchart(diagram: str) -> list[str]:
    """Validate the restricted Mermaid flowchart format used by this app."""
    errors: list[str] = []
    lines = diagram.strip().splitlines()

    if not lines:
        return ["Diagram is empty."]

    if lines[0].strip() != "flowchart LR":
        errors.append("Diagram must start with 'flowchart LR'.")

    if "```" in diagram or "sequenceDiagram" in diagram or "participant " in diagram:
        errors.append(
            "Diagram contains Markdown fences or sequence-diagram syntax."
        )

    declared_nodes: set[str] = set()
    referenced_nodes: set[str] = set()
    seen_edges: set[str] = set()
    edge_count = 0

    for line_number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()

        if not stripped or stripped.startswith("%%"):
            continue

        if stripped.lower().startswith("style "):
            errors.append(
                f"Style directives are not supported in this restricted diagram format (line {line_number})."
            )
            continue

        if re.search(r"-->>|->>|==>|<--|<->|--x|--o", stripped):
            errors.append(
                f"Unsupported arrow syntax on line {line_number}; use --> only."
            )
            continue

        if EDGE_PATTERN.search(stripped):
            edge_count += 1
            normalized_edge = stripped
            if normalized_edge in seen_edges:
                errors.append(f"Duplicate edge declaration on line {line_number}.")
            seen_edges.add(normalized_edge)

            # Split each simple edge into its source and target.
            parts = EDGE_PATTERN.split(stripped)

            for part in parts:
                # Remove an optional edge label, e.g. |Upload PDF|.
                part = re.sub(r"\|[^|]*\|", "", part).strip()

                # The node ID is the first identifier in each segment.
                match = NODE_ID_PATTERN.match(part)
                if match:
                    node_id = match.group(0)
                    referenced_nodes.add(node_id)

                    # A node with an explicit shape/label is declared.
                    remainder = part[match.end():].lstrip()
                    if remainder.startswith(("[", "(", "{")):
                        declared_nodes.add(node_id)

        else:
            # Standalone declarations such as: client["Tenant"]
            match = re.match(
                r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*'
                r'(\["[^"]*"\]|\[[^\]]*\]|\("[^"]*"\)|\([^)]*\)|\{[^}]*\})',
                stripped,
            )
            if match:
                declared_nodes.add(match.group(1))

    if not referenced_nodes:
        errors.append("Diagram must contain at least one flowchart edge.")

    if edge_count > 30:
        errors.append(
            f"Diagram contains {edge_count} edges; keep the diagram concise with no more than 30 edges."
        )

    missing_nodes = referenced_nodes - declared_nodes
    if missing_nodes:
        errors.append(
            "Referenced nodes are not declared explicitly: "
            + ", ".join(sorted(missing_nodes))
        )

    return errors