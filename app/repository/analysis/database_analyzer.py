import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ConfidenceLevel, DatabaseFinding, EvidenceCategory
from app.repository.models import RepositorySnapshot


class DatabaseAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[DatabaseFinding]:
        findings: list[DatabaseFinding] = []
        seen: set[tuple[str, str, str]] = set()
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if not text:
                continue
            checks = (
                ("Entity Framework Core", "DbContext or Entity Framework usage", r"DbContext|EntityFrameworkCore|UseSqlServer|UseNpgsql|UseSqlite"),
                ("SQLAlchemy", "SQLAlchemy import or usage", r"sqlalchemy|create_engine|declarative_base"),
                ("Django ORM", "Django ORM usage", r"django\.db|models\.Model|objects\."),
                ("Repository persistence abstraction", "Persistence repository abstraction", r"\b(class|interface)\s+\w*(Repository|Persistence)\b|def\s+\w*(find|get|save|update|delete)\w*"),
            )
            for technology, evidence_type, pattern in checks:
                if re.search(pattern, text, re.IGNORECASE):
                    key = (technology, evidence_type, file.relative_path)
                    if key in seen:
                        continue
                    seen.add(key)
                    ref = evidence.add(file.relative_path, EvidenceCategory.database, f"{technology} evidence found: {evidence_type}.")
                    findings.append(DatabaseFinding(technology=technology, evidence_type=evidence_type, relative_path=file.relative_path, detail=evidence_type, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))

            for line_number, line in enumerate(text.splitlines(), 1):
                if re.search(r"(ConnectionStrings?|DATABASE_URL|DB_HOST|DB_NAME|POSTGRES|MYSQL|MONGODB|REDIS)", line, re.IGNORECASE):
                    match = re.search(r'["\']?([A-Za-z][A-Za-z0-9_.]*(?:ConnectionStrings?|DATABASE_URL|DB_HOST|DB_NAME|POSTGRES|MYSQL|MONGODB|REDIS)[A-Za-z0-9_.]*)["\']?', line, re.IGNORECASE)
                    key_name = match.group(1) if match else "database configuration key"
                    ref = evidence.add(file.relative_path, EvidenceCategory.database, f"Database configuration key {key_name} found; its value is redacted.", line_number=line_number)
                    findings.append(DatabaseFinding(technology="Database configuration", evidence_type="configuration key", relative_path=file.relative_path, detail=f"Configuration key: {key_name}", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.medium))
        return findings
