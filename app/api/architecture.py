
from fastapi import APIRouter, HTTPException

from app.agents.architecture_agent import ArchitectureAgent
from app.api.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
)
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/architecture", tags=["Architecture"])

architecture_agent = ArchitectureAgent()


@router.post("/design", response_model=ArchitectureResponse)
async def design_architecture(
    request: ArchitectureRequest,
) -> ArchitectureResponse:
    try:
        recommendation = await architecture_agent.design(
            request.requirements
        )

        return ArchitectureResponse(
            agent="ArchitectureAgent",
            model_provider=settings.model_provider.lower(),
            recommendation=recommendation,
        )

    except Exception as exc:
        # Log the exception in a later observability milestone.
        raise HTTPException(
            status_code=502,
            detail="Architecture generation failed. Check the model "
                   "configuration and application logs.",
        ) from exc
