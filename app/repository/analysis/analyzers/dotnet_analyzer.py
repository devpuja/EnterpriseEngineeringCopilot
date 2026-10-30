import re
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import TechnologyFinding, EvidenceCategory, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class DotNetAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[TechnologyFinding]:
        findings: list[TechnologyFinding] = []
        for file in snapshot.files:
            if file.extension.lower() not in {".cs", ".csproj", ".sln", ".slnx"}:
                continue
            text = reader.read_text(snapshot, file) or ""
            names = []
            if file.extension.lower() in {".cs", ".csproj", ".sln", ".slnx"}:
                names.append(".NET/C#")
            if "Microsoft.NET.Sdk.Web" in text or re.search(r"\b(ApiController|ControllerBase|WebApplication)\b", text):
                names.append("ASP.NET Core")
            if "DbContext" in text or "EntityFrameworkCore" in text:
                names.append("Entity Framework Core")
            for name in names:
                ref = evidence.add(file.relative_path, EvidenceCategory.technology, f"{name} evidence found.")
                findings.append(TechnologyFinding(name=name, category="framework" if name != ".NET/C#" else "language/platform", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
        return findings
