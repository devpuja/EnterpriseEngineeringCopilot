import logging

from fastapi import FastAPI

from app.api.architecture import router as architecture_router
from app.api.rag import router as rag_router
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