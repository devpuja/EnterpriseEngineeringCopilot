import json
import logging
import re
from datetime import datetime, timezone

from app.observability.context import current_context


_SAFE_FIELDS = frozenset({
    "event", "request_id", "correlation_id", "trace_id", "span_id", "actor",
    "agent", "workflow", "operation", "provider", "model", "duration_ms",
    "outcome", "error_category", "stage", "status_code", "retry_count",
    "resource_id", "format", "count",
})


def redact_metadata(value: object) -> object:
    from app.security import SecretRedactionFilter

    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if re.search(r"(?i)secret|token|password|authorization|api.?key", str(key))
                else redact_metadata(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_metadata(item) for item in value]
    if isinstance(value, str):
        return SecretRedactionFilter._redact(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return type(value).__name__


class StructuredFormatter(logging.Formatter):
    def __init__(self, output_format: str = "text") -> None:
        super().__init__()
        self.output_format = output_format

    def format(self, record: logging.LogRecord) -> str:
        message = str(redact_metadata(record.getMessage()))
        if not record.name.startswith("app."):
            # Dependency DEBUG messages can contain HTTP bodies or signed URLs.
            message = "event=dependency_log"
        fields: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": "application_log",
            **{key: value for key, value in current_context().items() if key in _SAFE_FIELDS},
        }
        event_match = re.search(r"\bevent=([a-zA-Z0-9_.-]+)", message)
        if event_match:
            fields["event"] = event_match.group(1)
        metadata = getattr(record, "event_fields", {})
        if isinstance(metadata, dict):
            fields.update({
                key: redact_metadata(value)
                for key, value in metadata.items() if key in _SAFE_FIELDS
            })
        fields["message"] = message
        if record.exc_info:
            fields["error_category"] = record.exc_info[0].__name__
            # Exception messages and locals can contain complete provider output.
            frames = []
            traceback = record.exc_info[2]
            while traceback:
                frames.append({
                    "function": traceback.tb_frame.f_code.co_name,
                    "line": traceback.tb_lineno,
                })
                traceback = traceback.tb_next
            fields["exception_frames"] = frames
        if self.output_format == "json":
            return json.dumps(fields, ensure_ascii=True, allow_nan=False)
        context = " ".join(
            f"{key}={value}" for key, value in fields.items()
            if key not in {"timestamp", "level", "component", "message", "exception_frames"}
        )
        return f"{fields['timestamp']} | {record.levelname} | {record.name} | {context} {message}"


def configure_logging(level: str, output_format: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter(output_format))
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    for name in ("openai", "httpx", "httpx2", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info("event=%s", event, extra={"event_fields": {"event": event, **fields}})
