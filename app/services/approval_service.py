
"""In-memory human-approval workflow for simulated protected actions."""

from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class SimulatedActionArguments(BaseModel):
    """Arguments for the harmless demonstration action."""

    model_config = ConfigDict(frozen=True)

    target: str = Field(min_length=1, max_length=100)
    proposed_value: str = Field(min_length=1, max_length=200)


class ApprovalRequest(BaseModel):
    """An immutable snapshot of an approval request."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_name: str
    arguments: SimulatedActionArguments
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    result: str | None = None


class ApprovalStateError(ValueError):
    """Raised when an approval request has an invalid state transition."""


class ApprovalRequestNotFoundError(LookupError):
    """Raised when an approval request does not exist."""


class ApprovalService:
    """Manage approval requests in process memory."""

    TOOL_NAME = "simulate_configuration_change"

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = RLock()

    def create_request(self, *, target: str, proposed_value: str) -> ApprovalRequest:
        arguments = SimulatedActionArguments(
            target=target.strip(),
            proposed_value=proposed_value.strip(),
        )

        request = ApprovalRequest(
            request_id=str(uuid4()),
            tool_name=self.TOOL_NAME,
            arguments=arguments,
            status=ApprovalStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._requests[request.request_id] = request

        return request


    def get_request(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )
            return request


    def list_pending(self) -> list[ApprovalRequest]:
        with self._lock:
            return [
                request
                for request in self._requests.values()
                if request.status == ApprovalStatus.PENDING
            ]

    def decide(self, request_id: str, *, approved: bool, reviewer: str, reason: str | None = None) -> ApprovalRequest:
        reviewer = reviewer.strip()
        if not reviewer or len(reviewer) > 100:
            raise ValueError("Reviewer must contain 1 to 100 characters.")

        if reason is not None:
            reason = reason.strip()
            if len(reason) > 500:
                raise ValueError("Decision reason cannot exceed 500 characters.")
            reason = reason or None

        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )

            if request.status != ApprovalStatus.PENDING:
                raise ApprovalStateError(
                    "Only pending requests can receive a decision."
                )

            updated = request.model_copy(
                update={
                    "status": (
                        ApprovalStatus.APPROVED
                        if approved
                        else ApprovalStatus.REJECTED
                    ),
                    "decided_at": datetime.now(timezone.utc),
                    "decided_by": reviewer,
                    "decision_reason": reason,
                }
            )
            self._requests[request_id] = updated
            return updated


    def execute_simulated_action(self, request_id: str) -> ApprovalRequest:
        """Record a simulated execution; never modify a real resource."""

        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )

            if request.status != ApprovalStatus.APPROVED:
                raise ApprovalStateError(
                    "Only approved requests can be executed."
                )

            result = (
                "SIMULATION ONLY: would set "
                f"'{request.arguments.target}' to "
                f"'{request.arguments.proposed_value}'."
            )

            updated = request.model_copy(
                update={
                    "status": ApprovalStatus.EXECUTED,
                    "result": result,
                }
            )
            self._requests[request_id] = updated
            return updated


approval_service = ApprovalService()