"""Local engineering-tool API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.diagram_tool_agent import DiagramToolAgent
from app.api.schemas import DiagramToolRequest, DiagramToolResponse
from app.security import (
    Role,
    UserPrincipal,
    audit_security_event,
    require_roles,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/engineering-tools",
    tags=["Engineering Tools"],
)

diagram_tool_agent = DiagramToolAgent()


@router.post("/diagram-review", response_model=DiagramToolResponse)
async def review_diagram(
    request: DiagramToolRequest,
    principal: UserPrincipal = Depends(
        require_roles(Role.ADMINISTRATOR, Role.ARCHITECT, Role.DEVELOPER, Role.ANALYST)
    ),
) -> DiagramToolResponse:
    """Use the MAF function tool to validate and explain a Mermaid diagram."""
    audit_security_event("tool_invocation", principal=principal, resource_id="validate_architecture_diagram")
    try:
        answer = await diagram_tool_agent.review_diagram(request.diagram)
        return DiagramToolResponse(answer=answer)
    except ValueError as exc:
        logger.warning("Diagram tool agent returned an invalid response: %s", type(exc).__name__)
        
        raise HTTPException(
            status_code=502,
            detail="The diagram validation agent returned an invalid response.",
        ) from exc

    except TimeoutError as exc:
        logger.warning(
            "Diagram validation timed out; error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=504,
            detail="Diagram validation timed out. Please try again.",
        ) from exc
        
    except Exception as exc:
        logger.exception(
            "Diagram validation tool workflow failed; error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Diagram validation failed. Check application logs.",
        ) from exc
