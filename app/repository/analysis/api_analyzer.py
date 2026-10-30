import json
import re

from app.repository.analysis.contracts import RepositoryContentReader
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.models import ApiEndpointFinding, EvidenceCategory, ConfidenceLevel
from app.repository.models import RepositorySnapshot


class APIAnalyzer:
    def analyze(self, snapshot: RepositorySnapshot, reader: RepositoryContentReader, evidence: EvidenceCollector) -> list[ApiEndpointFinding]:
        findings: list[ApiEndpointFinding] = []
        for file in snapshot.files:
            text = reader.read_text(snapshot, file) or ""
            if not text:
                continue
            lines = text.splitlines()
            if file.extension.lower() == ".cs":
                for line_number, line in enumerate(lines, 1):
                    route_match = re.search(r'\[Route(?:Attribute)?\s*\(\s*"([^"]*)"', line, re.IGNORECASE)
                    method_match = re.search(r'\[(Http(Get|Post|Put|Delete|Patch))(?:Attribute)?(?:\s*\(\s*"([^"]*)"\s*\))?', line, re.IGNORECASE)
                    if method_match:
                        method = method_match.group(1).upper()
                        route = method_match.group(2) or ""
                        class_route = next((m.group(1) for m in re.findall(r'\[Route(?:Attribute)?\s*\(\s*"([^"]*)"', text[:text.find(line) if text.find(line) >= 0 else 0])), "")
                        full_route = "/" + "/".join(part.strip("/") for part in (class_route, route) if part.strip("/"))
                        ref = evidence.add(file.relative_path, EvidenceCategory.api, f"{method} ASP.NET Core route declared.", line_number=line_number, confidence=ConfidenceLevel.high)
                        findings.append(ApiEndpointFinding(exposure="exposed", method=method, route=full_route, relative_path=file.relative_path, framework="ASP.NET Core", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
            if file.extension.lower() == ".py":
                for line_number, line in enumerate(lines, 1):
                    for framework, pattern in (
                        ("FastAPI", r'@\w+\.(get|post|put|delete|patch)\(\s*[rubfRUBF]*["\']([^"\']+)'),
                        ("Flask", r'@\w+\.route\(\s*[rubfRUBF]*["\']([^"\']+)'),
                    ):
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            if framework == "FastAPI":
                                method, route = match.group(1).upper(), match.group(2)
                            else:
                                method, route = "GET", match.group(1)
                            ref = evidence.add(file.relative_path, EvidenceCategory.api, f"{framework} route declaration found.", line_number=line_number, confidence=ConfidenceLevel.high)
                            findings.append(ApiEndpointFinding(exposure="exposed", method=method, route=route, relative_path=file.relative_path, framework=framework, evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.high))
                    if "uvicorn.run(" in line:
                        ref = evidence.add(file.relative_path, EvidenceCategory.entry_point, "uvicorn application entry point found.", line_number=line_number)

            for line_number, line in enumerate(lines, 1):
                for method in ("fetch", "axios.get", "axios.post", "axios.put", "axios.delete", "axios.patch"):
                    if method in line:
                        route_match = re.search(r"['\"`]([^'\"`]*(?:/api/|https?://)[^'\"`]*)['\"`]", line)
                        route = route_match.group(1) if route_match else "unknown"
                        http_method = "GET" if method == "fetch" else method.split(".")[-1].upper()
                        ref = evidence.add(file.relative_path, EvidenceCategory.api, "Client-side HTTP request found; this API may be consumed, not implemented.", line_number=line_number, confidence=ConfidenceLevel.high)
                        findings.append(ApiEndpointFinding(exposure="consumed", method=http_method, route=route, relative_path=file.relative_path, framework="HTTP client", evidence_references=[ref.evidence_id], confidence=ConfidenceLevel.medium))
        return findings


ApiAnalyzer = APIAnalyzer
