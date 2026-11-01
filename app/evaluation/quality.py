import logging
from contextlib import contextmanager
from typing import Iterator

from app.observability.logging import log_event
from app.observability.metrics import operational_store
from app.observability.models import QualityOutcome


logger = logging.getLogger(__name__)


def quality_gate(gate: str, valid: bool, *, hard: bool, category: str) -> QualityOutcome:
    outcome = QualityOutcome(gate=gate, status="passed" if valid else "failed",
                             hard=hard, category=None if valid else category)
    _record_outcome(outcome)
    if not valid and hard:
        raise ValueError(f"Quality gate '{gate}' rejected the output.")
    return outcome


def _record_outcome(outcome: QualityOutcome) -> None:
    operational_store.record("quality", summary=outcome.model_dump())
    log_event(logger, "quality_gate_completed", operation=outcome.gate,
              outcome=outcome.status, error_category=outcome.category)


@contextmanager
def validation_gate(gate: str) -> Iterator[None]:
    """Observe existing validators without changing their exception contracts."""
    try:
        yield
    except ValueError as exc:
        _record_outcome(QualityOutcome(gate=gate, status="failed", hard=True, category=type(exc).__name__))
        raise
    else:
        _record_outcome(QualityOutcome(gate=gate, status="passed", hard=True))
