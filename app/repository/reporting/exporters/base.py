import re
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
