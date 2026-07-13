import logging

from fastapi import APIRouter, Depends, Request

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


def get_summarization_service(
    settings: Settings = Depends(get_settings),
) -> SummarizationService:
    llm_client = OpenAILLMClient(settings)
    return SummarizationService(llm_client)


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
