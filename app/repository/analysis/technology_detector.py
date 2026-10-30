import json
import re

from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ConfidenceLevel, EvidenceCategory, TechnologyFinding
from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.models import RepositorySnapshot


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

        for file in snapshot.files:
            text = reader.read_text(snapshot, file)
            name = file.file_name.lower()
            suffix = file.extension.lower()
            if suffix in {".cs", ".csproj", ".sln", ".slnx"}:
                add(".NET/C#", "language/platform", file.relative_path, ".NET/C# source or project evidence found.")
            if suffix == ".csproj" or suffix in {".sln", ".slnx"}:
                add("ASP.NET Core project", "framework", file.relative_path, "A .NET project or solution manifest was discovered.", ConfidenceLevel.medium)
            if text and suffix == ".csproj":
                if "Microsoft.NET.Sdk.Web" in text:
                    add("ASP.NET Core", "framework", file.relative_path, "The project uses the ASP.NET Core Web SDK.")
                if "Microsoft.EntityFrameworkCore" in text:
                    add("Entity Framework Core", "persistence", file.relative_path, "Entity Framework Core package or framework evidence found.")
            if text and suffix in {".cs"}:
                if re.search(r"\b(Controller|ApiController)\b", text):
                    add("ASP.NET Core Web API", "framework", file.relative_path, "Controller/API type evidence found in C# source.")
                if "EntityFrameworkCore" in text or "DbContext" in text:
                    add("Entity Framework Core", "persistence", file.relative_path, "DbContext or Entity Framework Core API usage found.")

            if suffix == ".py" or name in {"pyproject.toml", "requirements.txt", "setup.cfg", "setup.py"}:
                if text:
                    if name == "pyproject.toml" or name == "requirements.txt" or name == "setup.cfg" or name == "setup.py":
                        add("Python", "language", file.relative_path, "Python project configuration was discovered.")
                    else:
                        add("Python", "language", file.relative_path, "Python source file was discovered.")
                    lower = text.lower()
                    if "fastapi" in lower or re.search(r"from fastapi|import fastapi", lower):
                        add("FastAPI", "framework", file.relative_path, "FastAPI dependency or import evidence found.")
                    if re.search(r"from flask|import flask|flask\.", lower):
                        add("Flask", "framework", file.relative_path, "Flask dependency or import evidence found.")
                    if "django" in lower or "django.urls" in lower:
                        add("Django", "framework", file.relative_path, "Django dependency or URL/framework evidence found.")
                    if "sqlalchemy" in lower:
                        add("SQLAlchemy", "persistence", file.relative_path, "SQLAlchemy evidence found.")

            if name == "angular.json":
                add("Angular", "framework", file.relative_path, "angular.json configuration was discovered.")
            if name == "package.json" and text:
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    package = {}
                dependencies = {
                    **package.get("dependencies", {}),
                    **package.get("devDependencies", {}),
                }
                if "@angular/core" in dependencies:
                    add("Angular", "framework", file.relative_path, "package.json declares @angular/core.")
                if "react" in dependencies:
                    add("React", "framework", file.relative_path, "package.json declares react.")
                if "next" in dependencies:
                    add("Next.js", "framework", file.relative_path, "package.json declares next.")
                if "@nestjs/core" in dependencies:
                    add("NestJS", "framework", file.relative_path, "package.json declares @nestjs/core.")

            if text and suffix in {".jsx", ".tsx"}:
                if re.search(r"from ['\"]react['\"]|require\(['\"]react['\"]\)", text):
                    add("React", "framework", file.relative_path, "React is imported by a JSX/TSX module.")
            if text and suffix in {".ts", ".tsx"}:
                if "@angular/" in text:
                    add("Angular", "framework", file.relative_path, "Angular package imports were found in TypeScript source.")

        unique = {(item.name, item.category): item for item in findings}
        return list(unique.values()), technologies
