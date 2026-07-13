from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Production-like FastAPI service skeleton for LLM text summarization.",
)

app.include_router(router)
