import json
import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ConfidenceLevel, EvidenceCategory, IntegrationFinding
from app.repository.models import RepositorySnapshot


class IntegrationAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[IntegrationFinding]:
        findings: list[IntegrationFinding] = []
        patterns = (
            ("REST/HTTP client", "HTTP", r"HttpClient|requests\.|axios|fetch\(|httpx|RestTemplate|okhttp"),
            ("Message broker", "messaging", r"kafka|rabbitmq|nats|servicebus|azure.*messaging|amqp|pika"),
            ("Cloud SDK", "cloud", r"boto3|azure\.identity|Azure\.Messaging|Google\.Cloud|aws-sdk|@aws-sdk"),
            ("Authentication provider", "authentication", r"oauth|oidc|identityserver|auth0|msal|jwt"),
            ("Object/file storage", "storage", r"azure.*storage|boto3.*s3|s3client|blobstorage|google.*storage|cloudinary"),
        )
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if not text:
                continue
            for name, integration_type, pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    line_number = text[:match.start()].count("\n") + 1
                    ref = evidence.add(file.relative_path, EvidenceCategory.integration, f"{name} evidence found in source or configuration.", line_number=line_number, confidence=ConfidenceLevel.high)
                    findings.append(IntegrationFinding(name=name, integration_type=integration_type, status="confirmed", relative_path=file.relative_path, detail=f"{name} API or package usage is present in repository evidence.", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))

            if file.file_name == "package.json":
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    continue
                deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                for package_name in deps:
                    if any(token in package_name.lower() for token in ("axios", "firebase", "auth0", "aws-sdk", "azure")):
                        ref = evidence.add(file.relative_path, EvidenceCategory.integration, f"External integration package {package_name} declared.")
                        findings.append(IntegrationFinding(name=package_name, integration_type="package dependency", status="confirmed", relative_path=file.relative_path, detail="Declared external integration package.", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
        return findings
