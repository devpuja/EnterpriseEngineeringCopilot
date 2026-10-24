
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.orchestrator.architecture_orchestrator import ArchitectureOrchestrator
from app.api.schemas import ArchitectureRequest, ArchitectureResponse
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/architecture",
    tags=["Architecture"],
)

architecture_agent = ArchitectureOrchestrator()


@router.post("/design", response_model=ArchitectureResponse)
async def design_architecture(request: ArchitectureRequest) -> ArchitectureResponse:
    request_id = str(uuid4())
    started_at = time.perf_counter()
    provider = settings.model_provider.lower()

    logger.info(
        "event=architecture_generation_started request_id=%s provider=%s",
        request_id,
        provider,
    )

    try:
        response = await architecture_agent.design(
            requirements=request.requirements,
            model_provider=provider,
        )

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        logger.info(
            "event=architecture_generation_succeeded "
            "request_id=%s provider=%s duration_ms=%.2f",
            request_id,
            provider,
            duration_ms,
        )

        return response

    except ValueError as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)


        logger.warning(
            "event=architecture_generation_invalid_output "
            "request_id=%s provider=%s duration_ms=%.2f "
            "error_type=%s error=%s",
            request_id,
            provider,
            duration_ms,
            type(exc).__name__,
            str(exc),
        )


        raise HTTPException(
            status_code=502,
            detail="The model returned an invalid architecture response.",
        ) from exc

    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        logger.exception(
            "event=architecture_generation_failed "
            "request_id=%s provider=%s duration_ms=%.2f error_type=%s",
            request_id,
            provider,
            duration_ms,
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail="Architecture generation failed. Check application logs.",
        ) from exc