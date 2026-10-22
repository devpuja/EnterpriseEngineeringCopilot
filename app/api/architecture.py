
import logging

from fastapi import APIRouter, HTTPException

from app.agents.architecture_agent import ArchitectureAgent
from app.api.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/architecture",
    tags=["Architecture"],
)

architecture_agent = ArchitectureAgent()


@router.post("/design", response_model=ArchitectureResponse)
async def design_architecture(request: ArchitectureRequest) -> ArchitectureResponse:
    try:
        return await architecture_agent.design(
            requirements=request.requirements,
            model_provider=settings.model_provider,
        )

    except ValueError as exc:
        logger.warning("Architecture output validation failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="The model returned an invalid architecture response.",
        ) from exc

    except Exception as exc:
        logger.exception("Architecture generation failed")
        raise HTTPException(
            status_code=502,
            detail="Architecture generation failed. Check application logs.",
        ) from exc
