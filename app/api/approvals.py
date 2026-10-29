
"""Local human-approval API for simulated protected actions."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.approval_service import (
    ApprovalRequest,
    ApprovalRequestNotFoundError,
    # ApprovalService,
    ApprovalStateError,
    approval_service,
)

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["Human Approval"],
)


class CreateApprovalRequest(BaseModel):
    """Request a simulated configuration change."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=100)
    proposed_value: str = Field(min_length=1, max_length=200)


class ApprovalDecisionRequest(BaseModel):
    """Approve or reject a pending request."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)


@router.post("", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED)
def create_approval_request(request: CreateApprovalRequest) -> ApprovalRequest:
    """Create a pending simulated action request."""
    try:
        return approval_service.create_request(
            target=request.target,
            proposed_value=request.proposed_value,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[ApprovalRequest])
def list_pending_approval_requests() -> list[ApprovalRequest]:
    """List requests awaiting a decision."""
    return approval_service.list_pending()


@router.get("/{request_id}", response_model=ApprovalRequest)
def get_approval_request(request_id: str) -> ApprovalRequest:
    """Retrieve one approval request."""
    try:
        return approval_service.get_request(request_id)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        ) from exc


@router.post("/{request_id}/decision", response_model=ApprovalRequest)
def decide_approval_request(request_id: str, decision: ApprovalDecisionRequest) -> ApprovalRequest:
    """Record a reviewer's approval or rejection."""
    try:
        return approval_service.decide(
            request_id,
            approved=decision.approved,
            reviewer=decision.reviewer,
            reason=decision.reason,
        )
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        ) from exc
    except ApprovalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{request_id}/execute", response_model=ApprovalRequest)
def execute_approved_request(request_id: str) -> ApprovalRequest:
    """Execute the harmless simulation after approval."""
    try:
        return approval_service.execute_simulated_action(request_id)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        ) from exc
    except ApprovalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc