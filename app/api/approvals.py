
"""Local human-approval API for simulated protected actions."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.approval_service import (
    ApprovalRequest,
    ApprovalRequestNotFoundError,
    ApprovalStateError,
    approval_service,
)
from app.security import (
    Role,
    UserPrincipal,
    audit_security_event,
    require_roles,
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
    reason: str | None = Field(default=None, max_length=500)


@router.post("", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED)
def create_approval_request(
    request: CreateApprovalRequest,
    principal: UserPrincipal = Depends(
        require_roles(Role.ADMINISTRATOR, Role.ARCHITECT, Role.DEVELOPER)
    ),
) -> ApprovalRequest:
    """Create a pending simulated action request."""
    try:
        result = approval_service.create_request(
            target=request.target,
            proposed_value=request.proposed_value,
            owner_id=principal.owner_id,
        )
        audit_security_event(
            "approval_requested",
            principal=principal,
            resource_id=result.request_id,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[ApprovalRequest])
def list_pending_approval_requests(
    principal: UserPrincipal = Depends(
        require_roles(
            Role.ADMINISTRATOR,
            Role.ARCHITECT,
            Role.DEVELOPER,
            Role.ANALYST,
            Role.READ_ONLY,
        )
    ),
) -> list[ApprovalRequest]:
    """List requests awaiting a decision."""
    owner_id = (
        None
        if principal.roles.intersection({Role.ADMINISTRATOR, Role.ARCHITECT})
        else principal.owner_id
    )
    return approval_service.list_pending(owner_id=owner_id)


@router.get("/{request_id}", response_model=ApprovalRequest)
def get_approval_request(
    request_id: str,
    principal: UserPrincipal = Depends(
        require_roles(
            Role.ADMINISTRATOR,
            Role.ARCHITECT,
            Role.DEVELOPER,
            Role.ANALYST,
            Role.READ_ONLY,
        )
    ),
) -> ApprovalRequest:
    """Retrieve one approval request."""
    try:
        owner_id = (
            None
            if principal.roles.intersection({Role.ADMINISTRATOR, Role.ARCHITECT})
            else principal.owner_id
        )
        return approval_service.get_request(request_id, owner_id=owner_id)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        ) from exc


@router.post("/{request_id}/decision", response_model=ApprovalRequest)
def decide_approval_request(
    request_id: str,
    decision: ApprovalDecisionRequest,
    principal: UserPrincipal = Depends(
        require_roles(Role.ADMINISTRATOR, Role.ARCHITECT)
    ),
) -> ApprovalRequest:
    """Record a reviewer's approval or rejection."""
    try:
        result = approval_service.decide(
            request_id,
            approved=decision.approved,
            reviewer=principal.audit_id,
            reason=decision.reason,
            owner_id=None,
        )
        audit_security_event(
            "approval_reviewed",
            principal=principal,
            resource_id=request_id,
            outcome="approved" if decision.approved else "rejected",
        )
        return result
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
def execute_approved_request(
    request_id: str,
    principal: UserPrincipal = Depends(
        require_roles(Role.ADMINISTRATOR, Role.ARCHITECT)
    ),
) -> ApprovalRequest:
    """Execute the harmless simulation after approval."""
    try:
        result = approval_service.execute_simulated_action(
            request_id,
            owner_id=None,
        )
        audit_security_event("approval_executed", principal=principal, resource_id=request_id)
        return result
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


@router.post("/{request_id}/cancel", response_model=ApprovalRequest)
def cancel_approval_request(
    request_id: str,
    principal: UserPrincipal = Depends(
        require_roles(Role.ADMINISTRATOR, Role.ARCHITECT, Role.DEVELOPER)
    ),
) -> ApprovalRequest:
    """Cancel the caller's pending request."""
    try:
        result = approval_service.cancel_request(
            request_id,
            owner_id=principal.owner_id,
        )
        audit_security_event(
            "approval_cancelled",
            principal=principal,
            resource_id=request_id,
        )
        return result
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