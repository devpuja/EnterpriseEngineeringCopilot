from app.repository.analysis.models import (
    EvidenceCategory,
    EvidenceReference,
    ConfidenceLevel,
)


class EvidenceCollector:
    def __init__(self):
        self.items: list[EvidenceReference] = []
        self._seen: set[tuple[str, str | None, str, str, int | None]] = set()

    def add(
        self,
        relative_path: str,
        category: EvidenceCategory,
        explanation: str,
        *,
        symbol: str | None = None,
        line_number: int | None = None,
        line_end: int | None = None,
        confidence: ConfidenceLevel = ConfidenceLevel.medium,
    ) -> EvidenceReference:
        key = (relative_path, symbol, category.value, explanation, line_number)
        if key in self._seen:
            for item in self.items:
                if (
                    item.relative_path == relative_path
                    and item.category == category
                    and item.explanation == explanation
                    and item.symbol == symbol
                    and item.line_number == line_number
                ):
                    return item
        evidence_id = f"E{len(self.items) + 1:04d}"
        evidence = EvidenceReference(
            evidence_id=evidence_id,
            relative_path=relative_path,
            category=category,
            explanation=explanation,
            symbol=symbol,
            line_number=line_number,
            line_end=line_end,
            confidence=confidence,
        )
        self.items.append(evidence)
        self._seen.add(key)
        return evidence
