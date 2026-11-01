from collections import deque
from datetime import datetime, timezone
from threading import RLock

from opentelemetry import metrics
from pydantic import TypeAdapter

from app.observability.context import current_context
from app.observability.models import Observation


_observation_adapter = TypeAdapter(Observation)


class OperationalStore:
    """Bounded, process-local observations; never an audit ledger."""

    def __init__(self, capacity: int = 1000) -> None:
        if capacity <= 0:
            raise ValueError("Operational buffer capacity must be positive.")
        self._records: deque[Observation] = deque(maxlen=capacity)
        self._lock = RLock()

    def record(self, kind: str, **values: object) -> None:
        context = current_context()
        with self._lock:
            self._records.append(_observation_adapter.validate_python({
                "kind": kind, "timestamp": datetime.now(timezone.utc),
                "owner_id": context.get("owner_id"),
                "request_id": context.get("request_id"),
                "workflow": context.get("workflow"),
                "agent": context.get("agent"),
                **values,
            }))

    def records(self, owner_id: str, minutes: int = 60) -> list[Observation]:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._lock:
            return [
                item.model_copy(deep=True) for item in self._records
                if item.owner_id == owner_id and item.timestamp >= cutoff
            ]


operational_store = OperationalStore()


def record_operation(name: str, duration_ms: float, outcome: str) -> None:
    meter = metrics.get_meter(__name__)
    attributes = {"operation": name, "outcome": outcome}
    meter.create_counter("copilot.operation.count").add(1, attributes)
    meter.create_histogram("copilot.operation.duration", unit="ms").record(duration_ms, attributes)
    operational_store.record("operation", operation=name, duration_ms=duration_ms, outcome=outcome)


def record_retry(operation: str) -> None:
    metrics.get_meter(__name__).create_counter("copilot.retry.count").add(
        1, {"operation": operation}
    )
    operational_store.record("retry", operation=operation)
