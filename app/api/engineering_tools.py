"""Local engineering-tool API endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from app.agents.diagram_tool_agent import DiagramToolAgent
from app.api.schemas import DiagramToolRequest, DiagramToolResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/engineering-tools",
    tags=["Engineering Tools"],
)

diagram_tool_agent = DiagramToolAgent()


@router.post("/diagram-review", response_model=DiagramToolResponse)
async def review_diagram(request: DiagramToolRequest) -> DiagramToolResponse:
    """Use the MAF function tool to validate and explain a Mermaid diagram."""
    try:
        answer = await diagram_tool_agent.review_diagram(request.diagram)
        return DiagramToolResponse(answer=answer)
    except ValueError as exc:
        logger.warning("Diagram tool agent returned an invalid response: %s", exc)
        
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
