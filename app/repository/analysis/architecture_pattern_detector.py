import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ArchitecturePatternFinding, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class ArchitecturePatternDetector:
    def detect(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[ArchitecturePatternFinding]:
        patterns: list[ArchitecturePatternFinding] = []
        paths = {file.relative_path for file in snapshot.files}

        def add(name: str, explanation: str, files: list[str], confidence: ConfidenceLevel, limitation: str):
            patterns.append(ArchitecturePatternFinding(name=name, evidence=[explanation], relevant_files=files, explanation=explanation, confidence=confidence, limitations=limitation))
        di_files = []
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if re.search(r"AddScoped|AddSingleton|AddTransient|AddDbContext|@Inject|constructor\s*\([^)]*\)|Depends\(", text, re.IGNORECASE):
                di_files.append(file.relative_path)
        if di_files:
            add("Dependency Injection", "Static dependency registration, injection decorators, or constructor injection evidence was found.", di_files, ConfidenceLevel.high, "Dependency lifetime and runtime composition are not fully demonstrated statically.")

        repository_files: list[str] = []
        repository_markers = re.compile(
            r"\b(?:class|interface)\s+\w*Repository(?:\w*)\b|I\w*Repository\b|Repository<",
            re.IGNORECASE,
        )
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if repository_markers.search(text):
                repository_files.append(file.relative_path)
        if repository_files:
            add(
                "Repository Pattern",
                "Code declarations provide repository abstraction or implementation evidence.",
                repository_files,
                ConfidenceLevel.medium,
                "Static evidence confirms declarations but not every runtime access pattern.",
            )

        if not patterns:
            patterns.append(ArchitecturePatternFinding(
                name="Not determined",
                evidence=["No sufficiently specific architectural pattern evidence was found."],
                relevant_files=[],
                explanation="The repository does not contain enough static evidence for a reliable architectural pattern determination.",
                confidence=ConfidenceLevel.low,
                limitations="Static analysis cannot establish runtime topology or architectural intent.",
            ))
        return patterns
