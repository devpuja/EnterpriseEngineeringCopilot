import re

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.visualization.models import (
    DiagramEvidenceMap,
    DiagramEvidenceReference,
)


class EvidenceMapper:
    def map_evidence(
        self,
        analysis: RepositoryAnalysisResult,
        evidence_ids: list[str],
        finding_id: str | None = None,
    ) -> list[DiagramEvidenceReference]:
        by_id = {item.evidence_id: item for item in analysis.evidence}
        mapped: list[DiagramEvidenceReference] = []
        for evidence_id in dict.fromkeys(evidence_ids):
            evidence = by_id.get(evidence_id)
            if evidence is None:
                continue
            mapped.append(DiagramEvidenceReference(
                evidence_id=evidence.evidence_id,
                relative_path=evidence.relative_path,
                category=evidence.category,
                confidence=evidence.confidence,
                finding_id=finding_id,
                explanation=evidence.explanation,
                symbol=evidence.symbol,
                line_number=evidence.line_number,
                line_end=evidence.line_end,
            ))
        return mapped

    def evidence_map(
        self,
        analysis: RepositoryAnalysisResult,
        node_references: dict[str, list[str]],
        relationship_references: dict[str, list[str]],
    ) -> DiagramEvidenceMap:
        nodes = {
            key: self.map_evidence(analysis, ids)
            for key, ids in node_references.items()
        }
        relationships = {
            key: self.map_evidence(analysis, ids)
            for key, ids in relationship_references.items()
        }
        return DiagramEvidenceMap(nodes=nodes, relationships=relationships)

    def relative_paths(self, references: list[DiagramEvidenceReference]) -> list[str]:
        paths: list[str] = []
        for reference in references:
            path = reference.relative_path.replace("\\", "/").lstrip("/")
            if path and not re.match(r"^[A-Za-z]:/", path) and ".." not in path.split("/"):
                if path not in paths:
                    paths.append(path)
        return paths

    def map_paths(
        self,
        analysis: RepositoryAnalysisResult,
        relative_paths: list[str],
        finding_id: str | None = None,
    ) -> list[DiagramEvidenceReference]:
        mapped: list[DiagramEvidenceReference] = []
        seen: set[str] = set()
        for path in dict.fromkeys(relative_paths):
            for evidence in analysis.evidence:
                if evidence.relative_path.replace("\\", "/") != path.replace("\\", "/"):
                    continue
                if evidence.evidence_id in seen:
                    continue
                seen.add(evidence.evidence_id)
                mapped.append(DiagramEvidenceReference(
                    evidence_id=evidence.evidence_id,
                    relative_path=evidence.relative_path,
                    category=evidence.category,
                    confidence=evidence.confidence,
                    finding_id=finding_id,
                    explanation=evidence.explanation,
                    symbol=evidence.symbol,
                    line_number=evidence.line_number,
                    line_end=evidence.line_end,
                ))
        return mapped
