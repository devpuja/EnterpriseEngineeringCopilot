from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI

from app.api.architecture import router as architecture_router
from app.api.rag import router as rag_router
from app.api.engineering_tools import router as engineering_tools_router
from app.api.approvals import router as approvals_router
from app.api.repository_reports import router as repository_reports_router
from app.api.operations import router as operations_router
from app.config.settings import settings
from app.observability.logging import configure_logging
from app.observability.middleware import RequestContextMiddleware
from app.observability.telemetry import configure_telemetry, shutdown_telemetry

configure_logging(settings.log_level, settings.log_format)
configure_telemetry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await asyncio.to_thread(shutdown_telemetry)

app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="0.4.0",
    description="An agentic AI copilot for software architecture analysis and decision support.",
    swagger_ui_init_oauth=(
        {
            "clientId": settings.swagger_oauth_client_id,
            "scopes": [settings.swagger_oauth_scope],
            "usePkceWithAuthorizationCodeGrant": True,
        }
        if settings.swagger_oauth_client_id
        else None
    ),
)

app.add_middleware(RequestContextMiddleware)

app.include_router(architecture_router)
app.include_router(rag_router)
app.include_router(engineering_tools_router)
app.include_router(approvals_router)
app.include_router(repository_reports_router)
app.include_router(operations_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "application": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/")
async def root():
    return {"message": "Enterprise Engineering Copilot API", "docs": "/docs"}