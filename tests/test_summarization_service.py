import asyncio

import pytest

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

    async def summarize(self, text: str, max_sentences: int) -> str:
        if self.exc:
            raise self.exc
        return self.result


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
    service = SummarizationService(FakeLLMClient(exc=exc))

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


def test_service_raises_unavailable_when_fallback_fails() -> None:
    def broken_fallback(text: str, max_sentences: int) -> str:
        raise RuntimeError("internal fallback detail")

    service = SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout")),
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


def test_service_raises_unavailable_when_fallback_is_empty() -> None:
    service = SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout")),
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
