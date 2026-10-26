from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.agents.rag_answer_agent import RagAnswerAgent
from app.config.settings import settings
from app.rag.factory import get_rag_service
from app.rag.models import IngestResponse, QueryRequest, QueryResponse

bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    scheme_name="BearerAuth",
    auto_error=False,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/rag", tags=["RAG"], dependencies=[Depends(bearer_scheme)])


@lru_cache(maxsize=1)
def get_answer_agent() -> RagAnswerAgent:
    return RagAnswerAgent()


def _resolve_tenant_id(request: Request, x_tenant_id: str | None) -> str:
    backend = settings.rag_backend.strip().lower()
    if backend == "azure":
        # Do not trust a client-controlled tenant header for Azure data.
        # Phase 5 will install Entra ID middleware that sets request.state.tenant_id.
        trusted_tenant_id = getattr(request.state, "tenant_id", None)
        if not isinstance(trusted_tenant_id, str) or not trusted_tenant_id:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Azure RAG endpoints require trusted tenant context from Microsoft Entra ID middleware. "
                    "That middleware is a Phase 5 prerequisite; do not bypass this guard."
                ),
            )
        return trusted_tenant_id
    return x_tenant_id or "local-dev"


@router.post("/documents", response_model=IngestResponse, status_code=201)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    try:
        data = await file.read(25 * 1024 * 1024 + 1)
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="PDF exceeds the 25 MiB upload limit.")
        tenant_id = _resolve_tenant_id(request, x_tenant_id)
        result = await run_in_threadpool(
            get_rag_service().ingest_pdf,
            tenant_id=tenant_id,
            file_name=file.filename,
            pdf_bytes=data,
        )
        return IngestResponse(**result)
    except HTTPException:
        raise
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG document ingestion failed")
        raise HTTPException(status_code=502, detail="Document ingestion failed. Check application logs.") from exc
    finally:
        await file.close()


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    http_request: Request,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> QueryResponse:
    try:
        tenant_id = _resolve_tenant_id(http_request, x_tenant_id)
        service = get_rag_service()
        chunks = await run_in_threadpool(
            service.retrieve,
            tenant_id=tenant_id,
            question=request.question,
            top_k=request.top_k,
        )
        answer = await get_answer_agent().answer(request.question, chunks)
        return QueryResponse(answer=answer, citations=chunks, retrieval_count=len(chunks))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG query failed")
        raise HTTPException(status_code=502, detail="RAG query failed. Check application logs.") from exc
