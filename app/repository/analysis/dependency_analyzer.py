import json
import re
from pathlib import PurePosixPath

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ConfidenceLevel, DependencyFinding, EvidenceCategory
from app.repository.models import RepositorySnapshot


class DependencyAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        csproj_files = {file.relative_path: file for file in snapshot.files if file.extension.lower() == ".csproj"}
        python_files = {file.relative_path: file for file in snapshot.files if file.extension.lower() == ".py"}

        for path, file in csproj_files.items():
            text = reader.read_text(snapshot, file) or ""
            for match in re.finditer(r'<ProjectReference\s+Include="([^"]+)"', text, re.IGNORECASE):
                target = match.group(1).replace("\\", "/")
                normalized = str(PurePosixPath(path).parent / target)
                resolved = normalized in {PurePosixPath(p).as_posix() for p in csproj_files}
                line = text[:match.start()].count("\n") + 1
                ref = evidence.add(path, EvidenceCategory.dependency, f".NET project reference to {target}.", line_number=line)
                findings.append(DependencyFinding(source=path, target=normalized, dependency_type=".NET project reference", resolved=resolved, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high if resolved else ConfidenceLevel.low))

        module_names: dict[str, str] = {}
        for path in python_files:
            normalized = PurePosixPath(path)
            stem = normalized.with_suffix("").as_posix()
            module_names[stem.replace("/", ".")] = path
            if normalized.name == "__init__.py":
                package = normalized.parent.as_posix().replace("/", ".")
                if package and package != ".":
                    module_names[package] = path

        for path, file in python_files.items():
            text = reader.read_text(snapshot, file) or ""
            for line_number, line in enumerate(text.splitlines(), 1):
                match = re.match(
                    r"\s*(?:from\s+([.\w]+)\s+import|import\s+([A-Za-z_][\w.]*))",
                    line,
                )
                if not match:
                    continue
                imported = match.group(1) or match.group(2)
                source_module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
                source_parts = source_module.split(".")
                if source_module.endswith(".__init__"):
                    source_parts = source_module.split(".")[:-1]
                elif PurePosixPath(path).stem != "__init__":
                    source_parts = source_parts[:-1]

                if imported.startswith("."):
                    dot_count = len(imported) - len(imported.lstrip("."))
                    remainder = imported.lstrip(".")
                    if dot_count == 1:
                        package_parts = source_parts
                    else:
                        package_parts = source_parts[: max(0, len(source_parts) - (dot_count - 1))]
                    resolved_module = ".".join(part for part in package_parts + ([remainder] if remainder else []) if part)
                else:
                    resolved_module = imported

                target = module_names.get(resolved_module)
                if target:
                    ref = evidence.add(
                        path,
                        EvidenceCategory.dependency,
                        f"Internal Python import of {resolved_module}.",
                        symbol=resolved_module,
                        line_number=line_number,
                    )
                    findings.append(DependencyFinding(
                        source=path,
                        target=target,
                        dependency_type="Python import",
                        resolved=True,
                        evidence_references=[ref.evidence_id],
                        confidence=ConfidenceLevel.high,
                    ))

        for file in snapshot.files:
            if file.file_name != "package.json":
                continue
            text = reader.read_text(snapshot, file) or ""
            try:
                package = json.loads(text)
            except json.JSONDecodeError:
                continue
            for section in ("dependencies", "devDependencies"):
                for package_name in package.get(section, {}):
                    if package_name.startswith(".") or package_name.startswith("file:"):
                        target = package_name
                        ref = evidence.add(file.relative_path, EvidenceCategory.dependency, f"Local package dependency {package_name}.")
                        findings.append(DependencyFinding(source=file.relative_path, target=target, dependency_type="package dependency", resolved=True, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.medium))
        return findings
