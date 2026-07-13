import logging
from collections.abc import Callable
from typing import Optional, Protocol

from app.cache import CachedSummary, TTLCache, build_cache_key, cache_key_prefix
from app.core.config import Settings
from app.exceptions import (
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMTemporaryError,
    LLMUnexpectedError,
    ServiceUnavailableError,
)
from app.fallback import summarize_locally
from app.llm.client import PROMPT_VERSION
from app.postprocessing import clean_model_output
from app.schemas import SummarizeResponse, SummarySource


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def summarize(self, text: str, max_sentences: int) -> str: ...


class SummarizationService:
    def __init__(
        self,
        llm_client: LLMClient,
        settings: Optional[Settings] = None,
        cache: Optional[TTLCache] = None,
        fallback: Callable[[str, int], str] = summarize_locally,
    ) -> None:
        self._llm_client = llm_client
        self._settings = settings or Settings()
        self._cache = cache
        self._fallback = fallback

    async def summarize(
        self,
        text: str,
        max_sentences: int,
        request_id: str,
    ) -> SummarizeResponse:
        cache_key = self._build_cache_key(text, max_sentences)
        cached_summary = await self._get_cached_summary(cache_key, request_id)
        if cached_summary is not None:
            return SummarizeResponse(
                summary=cached_summary.summary,
                source=cached_summary.source,
                cached=True,
                degraded=cached_summary.degraded,
                request_id=request_id,
            )

        try:
            raw_summary = await self._llm_client.summarize(text, max_sentences)
            summary = clean_model_output(raw_summary)
            await self._set_cached_summary(cache_key, summary, request_id)
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

    def _build_cache_key(self, text: str, max_sentences: int) -> str:
        return build_cache_key(
            text=text,
            max_sentences=max_sentences,
            model=self._settings.openai_model,
            prompt_version=PROMPT_VERSION,
            max_output_tokens=self._settings.llm_max_output_tokens,
        )

    async def _get_cached_summary(
        self,
        cache_key: str,
        request_id: str,
    ) -> Optional[CachedSummary]:
        if not self._settings.cache_enabled or self._cache is None:
            logger.debug(
                "Cache disabled",
                extra={
                    "event": "cache_disabled",
                    "request_id": request_id,
                    "cache_key_prefix": cache_key_prefix(cache_key),
                },
            )
            return None

        cached_summary = await self._cache.get(cache_key)
        cache_size = await self._cache.size()
        if cached_summary is None:
            logger.info(
                "Cache miss",
                extra={
                    "event": "cache_miss",
                    "request_id": request_id,
                    "cache_key_prefix": cache_key_prefix(cache_key),
                    "cache_ttl_seconds": self._cache.ttl_seconds,
                    "cache_size": cache_size,
                },
            )
            return None

        logger.info(
            "Cache hit",
            extra={
                "event": "cache_hit",
                "request_id": request_id,
                "cache_key_prefix": cache_key_prefix(cache_key),
                "cache_ttl_seconds": self._cache.ttl_seconds,
                "cache_size": cache_size,
            },
        )
        return cached_summary

    async def _set_cached_summary(
        self,
        cache_key: str,
        summary: str,
        request_id: str,
    ) -> None:
        if not self._settings.cache_enabled or self._cache is None:
            return

        await self._cache.set(
            cache_key,
            CachedSummary(
                summary=summary,
                source=SummarySource.llm,
                degraded=False,
            ),
        )
        logger.info(
            "Cache set",
            extra={
                "event": "cache_set",
                "request_id": request_id,
                "cache_key_prefix": cache_key_prefix(cache_key),
                "cache_ttl_seconds": self._cache.ttl_seconds,
                "cache_size": await self._cache.size(),
            },
        )
