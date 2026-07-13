import asyncio

import pytest

from app.cache import TTLCache
from app.core.config import Settings
from app.exceptions import (
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMTemporaryError,
    LLMUnexpectedError,
    ServiceUnavailableError,
)
from app.schemas import SummarySource
from app.services.summarization import SummarizationService


class FakeLLMClient:
    def __init__(self, result: str = "Clean summary.", exc: Exception = None) -> None:
        self.result = result
        self.exc = exc
        self.calls = 0

    async def summarize(self, text: str, max_sentences: int) -> str:
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_settings(**kwargs) -> Settings:
    values = {
        "cache_enabled": True,
        "cache_ttl_seconds": 10,
        "cache_max_size": 10,
        "openai_model": "test-model",
        "llm_max_output_tokens": 128,
    }
    values.update(kwargs)
    return Settings(**values)


def test_service_returns_successful_llm_result() -> None:
    service = SummarizationService(FakeLLMClient(" Summary: Clean summary. "))

    response = asyncio.run(
        service.summarize(
            text="This is a valid text for summarization.",
            max_sentences=3,
            request_id="rid-1",
        )
    )

    assert response.summary == "Clean summary."
    assert response.source is SummarySource.llm
    assert response.cached is False
    assert response.degraded is False
    assert response.request_id == "rid-1"


def test_successful_llm_result_is_written_to_cache() -> None:
    llm = FakeLLMClient("Clean summary.")
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(llm, settings=make_settings(), cache=cache)

    response = asyncio.run(
        service.summarize(
            text="This is a valid text for summarization.",
            max_sentences=3,
            request_id="rid-cache-1",
        )
    )

    assert response.cached is False
    assert llm.calls == 1
    assert asyncio.run(cache.size()) == 1


def test_second_identical_call_uses_cache_with_new_request_id() -> None:
    llm = FakeLLMClient("Clean summary.")
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(llm, settings=make_settings(), cache=cache)
    text = "This is a valid text for summarization."

    first = asyncio.run(service.summarize(text, 3, "rid-first"))
    second = asyncio.run(service.summarize(text, 3, "rid-second"))

    assert llm.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert second.summary == first.summary
    assert second.request_id == "rid-second"
    assert first.request_id != second.request_id


def test_cache_entry_expires_and_llm_is_called_again() -> None:
    clock = FakeClock()
    llm = FakeLLMClient("Clean summary.")
    cache = TTLCache(ttl_seconds=10, max_size=10, clock=clock)
    service = SummarizationService(llm, settings=make_settings(), cache=cache)
    text = "This is a valid text for summarization."

    first = asyncio.run(service.summarize(text, 3, "rid-first"))
    clock.advance(11)
    second = asyncio.run(service.summarize(text, 3, "rid-second"))

    assert llm.calls == 2
    assert first.cached is False
    assert second.cached is False


def test_changed_max_sentences_gets_separate_cache_entry() -> None:
    llm = FakeLLMClient("Clean summary.")
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(llm, settings=make_settings(), cache=cache)
    text = "First fact. Second fact. Third fact."

    asyncio.run(service.summarize(text, 2, "rid-first"))
    response = asyncio.run(service.summarize(text, 3, "rid-second"))

    assert llm.calls == 2
    assert response.cached is False
    assert asyncio.run(cache.size()) == 2


def test_disabled_cache_never_reads_or_writes() -> None:
    llm = FakeLLMClient("Clean summary.")
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(
        llm,
        settings=make_settings(cache_enabled=False),
        cache=cache,
    )
    text = "This is a valid text for summarization."

    first = asyncio.run(service.summarize(text, 3, "rid-first"))
    second = asyncio.run(service.summarize(text, 3, "rid-second"))

    assert llm.calls == 2
    assert first.cached is False
    assert second.cached is False
    assert asyncio.run(cache.size()) == 0


@pytest.mark.parametrize(
    "exc",
    [
        LLMConfigurationError("missing key"),
        LLMTemporaryError("timeout"),
        LLMInvalidResponseError("empty"),
        LLMUnexpectedError("sdk"),
    ],
)
def test_service_uses_fallback_for_controlled_llm_errors(exc: Exception) -> None:
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(
        FakeLLMClient(exc=exc),
        settings=make_settings(),
        cache=cache,
    )

    response = asyncio.run(
        service.summarize(
            text="First fact. Second fact. Third fact.",
            max_sentences=2,
            request_id="rid-2",
        )
    )

    assert response.summary == "First fact. Second fact."
    assert response.source is SummarySource.fallback
    assert response.cached is False
    assert response.degraded is True
    assert response.request_id == "rid-2"
    assert asyncio.run(cache.size()) == 0


def test_service_raises_unavailable_when_fallback_fails() -> None:
    def broken_fallback(text: str, max_sentences: int) -> str:
        raise RuntimeError("internal fallback detail")

    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout")),
        settings=make_settings(),
        cache=cache,
        fallback=broken_fallback,
    )

    with pytest.raises(ServiceUnavailableError):
        asyncio.run(
            service.summarize(
                text="First fact. Second fact.",
                max_sentences=2,
                request_id="rid-3",
            )
        )
    assert asyncio.run(cache.size()) == 0


def test_service_raises_unavailable_when_fallback_is_empty() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout")),
        settings=make_settings(),
        cache=cache,
        fallback=lambda text, max_sentences: " ",
    )

    with pytest.raises(ServiceUnavailableError):
        asyncio.run(
            service.summarize(
                text="First fact. Second fact.",
                max_sentences=2,
                request_id="rid-4",
            )
        )
    assert asyncio.run(cache.size()) == 0


def test_invalid_llm_response_is_not_cached() -> None:
    llm = FakeLLMClient(result=" ")
    cache = TTLCache(ttl_seconds=10, max_size=10)
    service = SummarizationService(llm, settings=make_settings(), cache=cache)

    response = asyncio.run(
        service.summarize(
            text="First fact. Second fact.",
            max_sentences=2,
            request_id="rid-invalid",
        )
    )

    assert response.source is SummarySource.fallback
    assert response.cached is False
    assert asyncio.run(cache.size()) == 0
