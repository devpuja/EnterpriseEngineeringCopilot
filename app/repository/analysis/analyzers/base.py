from typing import Protocol

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.models import RepositorySnapshot


class BaseTechnologyAnalyzer(Protocol):
    def analyze(
        self,
        snapshot: RepositorySnapshot,
        reader: RepositoryContentReader,
        evidence: EvidenceCollector,
    ) -> object:
        ...
