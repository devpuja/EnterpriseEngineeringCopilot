import json
import re

from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ConfidenceLevel, EvidenceCategory, TechnologyFinding
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.models import RepositorySnapshot
from app.repository.analysis.analyzers.dotnet_analyzer import DotNetAnalyzer
from app.repository.analysis.analyzers.python_analyzer import PythonAnalyzer
from app.repository.analysis.analyzers.angular_analyzer import AngularAnalyzer
from app.repository.analysis.analyzers.react_analyzer import ReactAnalyzer


class TechnologyDetector:
    def detect(
        self,
        snapshot: RepositorySnapshot,
        reader: RepositoryContentReader,
        evidence: EvidenceCollector,
    ) -> tuple[list[TechnologyFinding], set[str]]:
        findings: list[TechnologyFinding] = []
        technologies: set[str] = set()

        def add(name: str, category: str, file_path: str, explanation: str, confidence=ConfidenceLevel.high):
            reference = evidence.add(
                file_path, EvidenceCategory.technology, explanation, confidence=confidence
            )
            technologies.add(name)
            findings.append(TechnologyFinding(
                name=name,
                category=category,
                evidence_references=[reference.evidence_id],
                confidence=confidence,
            ))
        specialized_analyzers = (
            DotNetAnalyzer(),
            PythonAnalyzer(),
            AngularAnalyzer(),
            ReactAnalyzer(),
        )
        for analyzer in specialized_analyzers:
            for finding in analyzer.analyze(snapshot, reader, evidence):
                key = (finding.name, finding.category)
                existing = next((item for item in findings if (item.name, item.category) == key), None)
                if existing:
                    existing.evidence_references.extend(
                        reference_id
                        for reference_id in finding.evidence_references
                        if reference_id not in existing.evidence_references
                    )
                    if finding.confidence.value != existing.confidence.value:
                        priorities = {ConfidenceLevel.low: 1, ConfidenceLevel.medium: 2, ConfidenceLevel.high: 3}
                        existing.confidence = max(existing.confidence, finding.confidence, key=lambda item: priorities[item])
                else:
                    findings.append(finding)
                technologies.add(finding.name)

        for file in snapshot.files:
            text = reader.read_text(snapshot, file)
            name = file.file_name.lower()
            if name == "package.json" and text:
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    package = {}
                dependencies = {
                    **package.get("dependencies", {}),
                    **package.get("devDependencies", {}),
                }
                if "next" in dependencies:
                    add("Next.js", "framework", file.relative_path, "package.json declares next.")
                if "@nestjs/core" in dependencies:
                    add("NestJS", "framework", file.relative_path, "package.json declares @nestjs/core.")

        unique = {(item.name, item.category): item for item in findings}
        return list(unique.values()), technologies
