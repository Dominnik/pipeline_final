import logging
from collections.abc import Callable
from typing import Protocol

from app.exceptions import (
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMTemporaryError,
    LLMUnexpectedError,
    ServiceUnavailableError,
)
from app.fallback import summarize_locally
from app.postprocessing import clean_model_output
from app.schemas import SummarizeResponse, SummarySource


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def summarize(self, text: str, max_sentences: int) -> str: ...


class SummarizationService:
    def __init__(
        self,
        llm_client: LLMClient,
        fallback: Callable[[str, int], str] = summarize_locally,
    ) -> None:
        self._llm_client = llm_client
        self._fallback = fallback

    async def summarize(
        self,
        text: str,
        max_sentences: int,
        request_id: str,
    ) -> SummarizeResponse:
        try:
            raw_summary = await self._llm_client.summarize(text, max_sentences)
            summary = clean_model_output(raw_summary)
            return SummarizeResponse(
                summary=summary,
                source=SummarySource.llm,
                cached=False,
                degraded=False,
                request_id=request_id,
            )
        except (
            LLMConfigurationError,
            LLMTemporaryError,
            LLMInvalidResponseError,
            LLMUnexpectedError,
        ) as exc:
            logger.info(
                "Fallback started",
                extra={
                    "event": "fallback_started",
                    "error_type": exc.__class__.__name__,
                    "request_id": request_id,
                },
            )
            fallback_summary = self._run_fallback(text, max_sentences, request_id)
            logger.info(
                "Fallback completed",
                extra={
                    "event": "fallback_completed",
                    "summary_length": len(fallback_summary),
                    "request_id": request_id,
                },
            )
            return SummarizeResponse(
                summary=fallback_summary,
                source=SummarySource.fallback,
                cached=False,
                degraded=True,
                request_id=request_id,
            )

    def _run_fallback(self, text: str, max_sentences: int, request_id: str) -> str:
        try:
            fallback_summary = self._fallback(text, max_sentences).strip()
        except Exception as exc:
            logger.error(
                "Fallback failed",
                extra={
                    "event": "request_failed",
                    "error_type": exc.__class__.__name__,
                    "request_id": request_id,
                },
            )
            raise ServiceUnavailableError("summarization unavailable") from exc

        if not fallback_summary:
            raise ServiceUnavailableError("summarization unavailable")

        return fallback_summary
