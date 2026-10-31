import logging

from fastapi import FastAPI

from app.api.architecture import router as architecture_router
from app.api.rag import router as rag_router
from app.api.engineering_tools import router as engineering_tools_router
from app.api.approvals import router as approvals_router
from app.api.repository_reports import router as repository_reports_router
from app.config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    force=True,
)

app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="An agentic AI copilot for software architecture analysis and decision support.",
)


app.include_router(architecture_router)
app.include_router(rag_router)
app.include_router(engineering_tools_router)
app.include_router(approvals_router)
app.include_router(repository_reports_router)


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