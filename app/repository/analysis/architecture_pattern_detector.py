import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ArchitecturePatternFinding, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class ArchitecturePatternDetector:
    def detect(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[ArchitecturePatternFinding]:
        patterns: list[ArchitecturePatternFinding] = []
        paths = {file.relative_path for file in snapshot.files}
        path_text = "\n".join(sorted(paths)).lower()

        def add(name: str, explanation: str, files: list[str], confidence: ConfidenceLevel, limitation: str):
            patterns.append(ArchitecturePatternFinding(name=name, evidence=[explanation], relevant_files=files, explanation=explanation, confidence=confidence, limitations=limitation))

        layered = [name for name in ("domain", "application", "infrastructure", "presentation") if name in path_text]
        if len(layered) >= 3:
            add("Layered Architecture", f"Source paths contain multiple conventional layers: {', '.join(sorted(layered))}.", [path for path in paths if any(layer in path.lower() for layer in layered)], ConfidenceLevel.medium, "Folder names alone do not prove dependency direction or runtime boundaries.")
        repository_files = [path for path in paths if re.search(r"(repository|repositories)", path, re.IGNORECASE)]
        if repository_files:
            add("Repository Pattern", "Repository-named source or abstraction paths are present.", repository_files, ConfidenceLevel.medium, "Confirm implementation code is required to distinguish a real repository abstraction from naming convention.")
        mvc_files = [path for path in paths if re.search(r"(controllers?|models?|views?)", path, re.IGNORECASE)]
        if mvc_files and len({match.group(1).lower() for match in re.finditer(r"(controllers?|models?|views?)", path_text, re.IGNORECASE)}) >= 2:
            add("MVC", "MVC-style controllers, models, or views are represented.", mvc_files, ConfidenceLevel.medium, "Directory naming may not reflect the framework's complete MVC implementation.")
        di_files = []
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if re.search(r"AddScoped|AddSingleton|AddTransient|AddDbContext|@Inject|constructor\s*\([^)]*\)|Depends\(", text, re.IGNORECASE):
                di_files.append(file.relative_path)
        if di_files:
            add("Dependency Injection", "Static dependency registration, injection decorators, or constructor injection evidence was found.", di_files, ConfidenceLevel.high, "Dependency lifetime and runtime composition are not fully demonstrated statically.")
        cqrs_files = [path for path in paths if re.search(r"(commands?|queries?|handlers?)", path, re.IGNORECASE)]
        if len(cqrs_files) >= 3:
            add("CQRS indicators", "Separate command, query, or handler source paths are present.", cqrs_files, ConfidenceLevel.low, "This evidence suggests but does not prove CQRS; no runtime behavior was analyzed.")
        event_files = [path for path in paths if re.search(r"(events?|publishers?|subscribers?|consumers?|handlers?)", path, re.IGNORECASE)]
        if event_files and any(marker in event_files.__repr__.lower() for marker in ("event", "publisher", "subscriber", "consumer")):
            add("Event-driven indicators", "Event, publisher, subscriber, or consumer source paths are present.", event_files, ConfidenceLevel.low, "Static source structure cannot prove asynchronous delivery, brokers, or runtime topology.")

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
