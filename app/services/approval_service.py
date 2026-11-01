
"""In-memory human-approval workflow for simulated protected actions."""

from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings
from app.security import audit_security_event


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


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
    owner_id: str | None = Field(default=None, exclude=True)
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

    def create_request(
        self,
        *,
        target: str,
        proposed_value: str,
        owner_id: str | None = None,
    ) -> ApprovalRequest:
        arguments = SimulatedActionArguments(
            target=target.strip(),
            proposed_value=proposed_value.strip(),
        )

        request = ApprovalRequest(
            request_id=str(uuid4()),
            tool_name=self.TOOL_NAME,
            arguments=arguments,
            owner_id=owner_id,
            status=ApprovalStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._requests[request.request_id] = request

        audit_security_event("approval_requested", resource_id=request.request_id)
        return request


    def _expire_if_needed(self, request: ApprovalRequest) -> ApprovalRequest:
        age_seconds = (datetime.now(timezone.utc) - request.created_at).total_seconds()
        if (
            request.status == ApprovalStatus.PENDING
            and age_seconds >= settings.approval_timeout_seconds
        ):
            request = request.model_copy(
                update={
                    "status": ApprovalStatus.EXPIRED,
                    "decided_at": datetime.now(timezone.utc),
                    "decision_reason": "Approval request expired.",
                }
            )
            self._requests[request.request_id] = request
        return request

    def get_request(
        self,
        request_id: str,
        owner_id: str | None = None,
    ) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or (
                owner_id is not None and request.owner_id != owner_id
            ):
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )
            return self._expire_if_needed(request)


    def list_pending(self, owner_id: str | None = None) -> list[ApprovalRequest]:
        with self._lock:
            requests = [
                self._expire_if_needed(request)
                for request in self._requests.values()
            ]
            return [
                request for request in requests
                if request.status == ApprovalStatus.PENDING
                and (owner_id is None or request.owner_id == owner_id)
            ]

    def decide(
        self,
        request_id: str,
        *,
        approved: bool,
        reviewer: str,
        reason: str | None = None,
        owner_id: str | None = None,
    ) -> ApprovalRequest:
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
            if request is None or (
                owner_id is not None and request.owner_id != owner_id
            ):
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )
            request = self._expire_if_needed(request)

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
        audit_security_event(
            "approval_decision",
            resource_id=request_id,
            outcome="approved" if approved else "rejected",
        )
        return updated


    def execute_simulated_action(
        self,
        request_id: str,
        owner_id: str | None = None,
    ) -> ApprovalRequest:
        """Record a simulated execution; never modify a real resource."""

        with self._lock:
            request = self._requests.get(request_id)
            if request is None or (
                owner_id is not None and request.owner_id != owner_id
            ):
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
        audit_security_event("approval_execution", resource_id=request_id)
        return updated

    def cancel_request(
        self,
        request_id: str,
        *,
        owner_id: str,
    ) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.owner_id != owner_id:
                raise ApprovalRequestNotFoundError(
                    "Approval request was not found."
                )
            request = self._expire_if_needed(request)
            if request.status != ApprovalStatus.PENDING:
                raise ApprovalStateError(
                    "Only pending requests can be cancelled."
                )
            updated = request.model_copy(
                update={
                    "status": ApprovalStatus.CANCELLED,
                    "decided_at": datetime.now(timezone.utc),
                    "decision_reason": "Cancelled by requester.",
                }
            )
            self._requests[request_id] = updated
        audit_security_event("approval_cancelled", resource_id=request_id)
        return updated


approval_service = ApprovalService()