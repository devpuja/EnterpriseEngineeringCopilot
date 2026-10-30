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

        for path, file in python_files.items():
            text = reader.read_text(snapshot, file) or ""
            for line_number, line in enumerate(text.splitlines(), 1):
                match = re.match(r"\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))", line)
                if not match:
                    continue
                module = (match.group(1) or match.group(2)).split(".", 1)[0]
                candidates = [key for key in module_names if key == module or key.startswith(module + ".")]
                if candidates:
                    target = module_names[min(candidates, key=len)]
                    ref = evidence.add(path, EvidenceCategory.dependency, f"Internal Python import of {module}.", symbol=module, line_number=line_number)
                    findings.append(DependencyFinding(source=path, target=target, dependency_type="Python import", resolved=True, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))

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
