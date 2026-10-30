import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import (
    ConfidenceLevel,
    EntryPointFinding,
    EvidenceCategory,
    ProjectFinding,
    ProjectStructureFinding,
)
from app.repository.models import RepositorySnapshot


class ProjectStructureAnalyzer:
    def analyze(
        self,
        snapshot: RepositorySnapshot,
        reader: RepositoryContentReader,
        evidence: EvidenceCollector,
    ) -> tuple[list[ProjectFinding], list[EntryPointFinding], ProjectStructureFinding]:
        projects: list[ProjectFinding] = []
        entries: list[EntryPointFinding] = []
        source_dirs: set[str] = set()
        test_dirs: set[str] = set()
        config_dirs: set[str] = set()
        infra_dirs: set[str] = set()
        shared: set[str] = set()

        for file in snapshot.files:
            path = file.relative_path
            parts = path.replace("\\", "/").split("/")
            lower_parts = {part.lower() for part in parts[:-1]}
            if lower_parts & {"src", "source", "app", "lib", "domain", "application", "infrastructure"}:
                for part in parts[:-1]:
                    if part.lower() in {"src", "source", "app", "lib"}:
                        source_dirs.add("/".join(parts[:parts.index(part) + 1]))
            if lower_parts & {"test", "tests", "__tests__", "spec"} or path.lower().startswith(("test_", "tests/")):
                test_dirs.update("/".join(parts[:i + 1]) for i, part in enumerate(parts[:-1]) if part.lower() in {"test", "tests", "__tests__", "spec"})
            if lower_parts & {"config", ".config", "properties", "settings"}:
                config_dirs.update("/".join(parts[:i + 1]) for i, part in enumerate(parts[:-1]) if part.lower() in {"config", ".config", "properties", "settings"})
            if lower_parts & {"docker", "kubernetes", "k8s", "terraform", "deploy", "deployment", "infra", "infrastructure"}:
                infra_dirs.update("/".join(parts[:i + 1]) for i, part in enumerate(parts[:-1]) if part.lower() in {"docker", "kubernetes", "k8s", "terraform", "deploy", "deployment", "infra", "infrastructure"})

            suffix = file.extension.lower()
            text = reader.read_text(snapshot, file)
            if suffix in {".csproj", ".sln", ".slnx"}:
                kind = "solution" if suffix in {".sln", ".slnx"} else "project"
                ref = evidence.add(path, EvidenceCategory.project, f"{kind.title()} manifest discovered.")
                projects.append(ProjectFinding(name=file.file_name, relative_path=path, kind=kind, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
            if file.file_name.lower() == "package.json" and text:
                ref = evidence.add(path, EvidenceCategory.project, "JavaScript package boundary discovered.")
                projects.append(ProjectFinding(name=file.file_name, relative_path=path, kind="package", evidence_references=[ref.evidence_id]))
            if file.file_name == "pyproject.toml" or file.file_name in {"requirements.txt", "setup.py", "setup.cfg"}:
                ref = evidence.add(path, EvidenceCategory.project, "Python project manifest or dependency configuration discovered.")
                projects.append(ProjectFinding(name=file.file_name, relative_path=path, kind="python-project", evidence_references=[ref.evidence_id]))

            if file.file_name.lower() in {"program.cs", "startup.cs"} and text:
                ref = evidence.add(path, EvidenceCategory.entry_point, "Application startup entry point source discovered.", symbol=file.file_name)
                entries.append(EntryPointFinding(relative_path=path, entry_point_type=".NET application startup", symbol=file.file_name, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
            if text and file.extension.lower() == ".py":
                if re.search(r"(app\s*=\s*FastAPI\(|Flask\(|DJANGO_SETTINGS_MODULE|uvicorn\.run|if\s+__name__\s*==\s*[\"']__main__[\"'])", text):
                    ref = evidence.add(path, EvidenceCategory.entry_point, "Python application entry-point or application object found.")
                    entries.append(EntryPointFinding(relative_path=path, entry_point_type="Python application entry point", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
            if file.file_name.lower() == "main.ts" and text:
                ref = evidence.add(path, EvidenceCategory.entry_point, "Angular bootstrap entry point source discovered.")
                entries.append(EntryPointFinding(relative_path=path, entry_point_type="Angular bootstrap", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
            if file.file_name.lower() in {"main.tsx", "main.jsx", "index.tsx", "index.jsx"} and text and ("react" in text.lower() or "react-dom" in text.lower()):
                ref = evidence.add(path, EvidenceCategory.entry_point, "React rendering entry point source discovered.")
                entries.append(EntryPointFinding(relative_path=path, entry_point_type="React rendering entry point", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))

            lower = path.lower()
            if any(marker in lower for marker in ("shared", "common", "core")) and len(parts) <= 4:
                shared.add("/".join(parts[:-1]) if len(parts) > 1 else ".")

        structure = ProjectStructureFinding(
            source_directories=sorted(source_dirs),
            test_directories=sorted(set(test_dirs)),
            config_locations=sorted(config_dirs),
            infrastructure_locations=sorted(infra_dirs),
            shared_libraries=sorted(shared),
            summary=f"Identified {len(projects)} project/package manifests and {len(entries)} application entry points from static evidence.",
        )
        return projects, entries, structure
