import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, Request

from app.cache import TTLCache
from app.core.config import Settings, get_settings
from app.llm.client import OpenAILLMClient
from app.schemas import (
    HealthResponse,
    HealthStatus,
    SummarizeRequest,
    SummarizeResponse,
)
from app.services.summarization import SummarizationService


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    llm_configured = settings.llm_configured
    status = HealthStatus.ok if llm_configured else HealthStatus.degraded

    return HealthResponse(
        status=status,
        app_env=settings.app_env,
        llm_configured=llm_configured,
    )


@lru_cache
def get_ttl_cache() -> TTLCache:
    settings = get_settings()
    return TTLCache(
        ttl_seconds=settings.cache_ttl_seconds,
        max_size=settings.cache_max_size,
    )


def get_summarization_service(
    settings: Settings = Depends(get_settings),
    cache: TTLCache = Depends(get_ttl_cache),
) -> SummarizationService:
    llm_client = OpenAILLMClient(settings)
    return SummarizationService(llm_client, settings=settings, cache=cache)


@router.post("/v1/summarize", response_model=SummarizeResponse)
async def summarize(
    payload: SummarizeRequest,
    request: Request,
    service: SummarizationService = Depends(get_summarization_service),
) -> SummarizeResponse:
    request_id = request.state.request_id
    logger.info(
        "Request received",
        extra={
            "event": "request_received",
            "request_id": request_id,
            "text_length": len(payload.text),
            "max_sentences": payload.max_sentences,
        },
    )
    return await service.summarize(
        text=payload.text,
        max_sentences=payload.max_sentences,
        request_id=request_id,
    )
