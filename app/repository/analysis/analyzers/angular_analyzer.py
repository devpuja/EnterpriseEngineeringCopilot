import json
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import TechnologyFinding, EvidenceCategory, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class AngularAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[TechnologyFinding]:
        findings = []
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            detected = file.file_name.lower() == "angular.json"
            if file.file_name.lower() == "package.json":
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    package = {}
                detected = "@angular/core" in {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            if detected or "@angular/" in text:
                ref = evidence.add(file.relative_path, EvidenceCategory.technology, "Angular evidence found.")
                findings.append(TechnologyFinding(name="Angular", category="framework", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
        return findings
