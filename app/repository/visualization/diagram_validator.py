import re
from dataclasses import dataclass

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.visualization.models import ArchitectureDiagram, DiagramType


NODE_DECLARATION = re.compile(r'^([A-Za-z][A-Za-z0-9_]*)\s*(?:\[|\(|\{)')
NODE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


@dataclass(frozen=True)
class DiagramValidationResult:
    valid: bool
    errors: list[str]
    limitations: tuple[str, ...] = (
        "Structural validation only; a Mermaid parser is not installed.",
    )


class DiagramValidator:
    def __init__(self, maximum_nodes: int = 30, maximum_edges: int = 30):
        self.maximum_nodes = maximum_nodes
        self.maximum_edges = maximum_edges

    def validate(
        self,
        diagram: ArchitectureDiagram,
        analysis: RepositoryAnalysisResult,
    ) -> DiagramValidationResult:
        errors: list[str] = []
        source = diagram.mermaid_source.strip()
        if not source:
            errors.append("Diagram Mermaid source is empty.")
        if not diagram.diagram_id or not diagram.title or not diagram.description:
            errors.append("Diagram required metadata is missing.")
        if not source.startswith("flowchart "):
            errors.append("Only Mermaid flowchart diagrams are supported by this implementation.")

        node_ids = [node.node_id for node in diagram.nodes]
        if len(set(node_ids)) != len(node_ids):
            errors.append("Diagram node identifiers must be unique.")
        if len(node_ids) > self.maximum_nodes:
            errors.append(f"Diagram exceeds the {self.maximum_nodes}-node complexity limit.")
        if len(diagram.relationships) > self.maximum_edges:
            errors.append(f"Diagram exceeds the {self.maximum_edges}-edge complexity limit.")
        known_nodes = set(node_ids)

        source_nodes: set[str] = set()
        edge_count = 0
        for line in source.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("%%"):
                continue
            declaration = NODE_DECLARATION.match(line)
            if declaration and "-->" not in line:
                source_nodes.add(declaration.group(1))
            if "-->" in line:
                edge_count += 1
                left, right = line.split("-->", 1)
                left_match = NODE_ID.match(left.strip())
                right_match = NODE_ID.match(re.sub(r"^\|[^|]*\|\s*", "", right.strip()))
                if not left_match or not right_match:
                    errors.append("Diagram contains an invalid relationship.")
                else:
                    source_nodes.update((left_match.group(0), right_match.group(0)))

        if edge_count == 0 and diagram.relationships:
            errors.append("Diagram relationships are missing from Mermaid source.")
        for relationship in diagram.relationships:
            if relationship.source_node_id not in known_nodes or relationship.target_node_id not in known_nodes:
                errors.append("A diagram relationship references an unknown node.")
        if known_nodes and source_nodes - known_nodes:
            errors.append("Mermaid source references undeclared nodes.")

        evidence_by_id = {item.evidence_id for item in analysis.evidence}
        for evidence_id in diagram.evidence_references:
            if evidence_id not in evidence_by_id:
                errors.append(f"Unknown evidence reference: {evidence_id}")
        for node in diagram.nodes:
            for evidence in node.evidence_references:
                if evidence.evidence_id not in evidence_by_id:
                    errors.append(f"Unknown node evidence reference: {evidence.evidence_id}")
        for relationship in diagram.relationships:
            for evidence in relationship.evidence_references:
                if evidence.evidence_id not in evidence_by_id:
                    errors.append(f"Unknown relationship evidence reference: {evidence.evidence_id}")

        return DiagramValidationResult(valid=not errors, errors=errors)
