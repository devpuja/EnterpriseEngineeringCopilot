import re
import html
import xml.etree.ElementTree as ET
from base64 import b64encode
from pathlib import Path

from app.repository.reporting.models import ArchitectureReport, ReportExportResult, ReportFormat


SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mssql|redis|amqp)://[^@\s]+@[^\s]+"),
)


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def safe_markdown_file_name(report: ArchitectureReport, extension: str) -> str:
    return f"architecture-report-{report.report_id}.{extension}"


def reportlab_text(text: str) -> str:
    safe = redact_sensitive_text(str(text)).replace("\x00", "")
    safe = html.escape(safe, quote=False)
    safe = re.sub(r"[\r\n]+", "<br/>", safe)
    safe = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", safe)
    return safe


def sanitize_svg(svg: str) -> str | None:
    if not svg:
        return None
    try:
        root = ET.fromstring(svg)
    except (ET.ParseError, ValueError):
        return None
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        return None
    dangerous_elements = {"script", "foreignobject", "iframe", "object", "embed"}
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1].lower() in dangerous_elements:
                parent.remove(child)
    for element in root.iter():
        for attribute in list(element.attrib):
            lower_name = attribute.lower()
            value = element.attrib[attribute].strip().lower()
            local_name = lower_name.rsplit("}", 1)[-1]
            if lower_name.startswith("on") or value.startswith("javascript:") or value.startswith("data:text/html"):
                del element.attrib[attribute]
            elif local_name == "style" and (
                "@import" in value or "url(" in value or "http://" in value or "https://" in value
                or "javascript:" in value
            ):
                del element.attrib[attribute]
            elif local_name == "href" and not (
                value.startswith("#")
                or value.startswith("data:image/png;base64,")
                or value.startswith("data:image/jpeg;base64,")
            ):
                del element.attrib[attribute]
            elif value.startswith(("http://", "https://", "//")) and local_name not in {"style"}:
                del element.attrib[attribute]
    return ET.tostring(root, encoding="unicode")


def svg_data_uri(svg: str) -> str | None:
    sanitized = sanitize_svg(svg)
    if sanitized is None:
        return None
    return "data:image/svg+xml;base64," + b64encode(sanitized.encode("utf-8")).decode("ascii")
