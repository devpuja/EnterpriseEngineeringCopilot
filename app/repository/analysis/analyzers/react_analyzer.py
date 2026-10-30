import json
import re
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import TechnologyFinding, EvidenceCategory, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class ReactAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[TechnologyFinding]:
        findings = []
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            detected = False
            if file.file_name.lower() == "package.json":
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    package = {}
                detected = "react" in {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            elif file.extension.lower() in {".jsx", ".tsx"}:
                detected = bool(re.search(r"from ['\"]react['\"]|require\(['\"]react['\"]\)", text))
            if detected:
                ref = evidence.add(file.relative_path, EvidenceCategory.technology, "React evidence found.")
                findings.append(TechnologyFinding(name="React", category="framework", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
        return findings
