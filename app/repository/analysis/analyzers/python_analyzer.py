import re
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import TechnologyFinding, EvidenceCategory, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class PythonAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[TechnologyFinding]:
        findings = []
        for file in snapshot.files:
            if file.extension.lower() != ".py" and file.file_name.lower() not in {"pyproject.toml", "requirements.txt", "setup.cfg", "setup.py"}:
                continue
            text = reader.read_text(snapshot, file) or ""
            lower = text.lower()
            names = ["Python"] if file.extension.lower() == ".py" or file.file_name.lower() in {"pyproject.toml", "requirements.txt", "setup.cfg", "setup.py"} else []
            if "fastapi" in lower: names.append("FastAPI")
            if re.search(r"from flask|import flask", lower): names.append("Flask")
            if "django" in lower: names.append("Django")
            if "sqlalchemy" in lower: names.append("SQLAlchemy")
            for name in names:
                ref = evidence.add(file.relative_path, EvidenceCategory.technology, f"{name} evidence found.")
                findings.append(TechnologyFinding(name=name, category="framework" if name not in {"Python"} else "language", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
        return findings
