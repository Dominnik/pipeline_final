import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.config import Settings
from app.exceptions import (
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMTemporaryError,
    LLMUnexpectedError,
)
from app.llm import client as client_module
from app.llm.client import OpenAILLMClient


class FakeResponses:
    def __init__(self, result: object = None, exc: Exception = None) -> None:
        self.result = result or SimpleNamespace(output_text="Summary.", id="resp_123")
        self.exc = exc
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


class FakeSDKClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def make_settings(**kwargs) -> Settings:
    values = {
        "openai_api_key": "test-key",
        "openai_model": "test-model",
        "openai_base_url": "https://example.test/v1",
        "llm_timeout_seconds": 7,
        "llm_max_retries": 4,
        "llm_max_output_tokens": 123,
    }
    values.update(kwargs)
    return Settings(**values)


def test_llm_client_sends_prompt_and_model_to_responses_api() -> None:
    responses = FakeResponses()
    llm_client = OpenAILLMClient(make_settings(), sdk_client=FakeSDKClient(responses))

    result = asyncio.run(llm_client.summarize("Input text for summary.", 2))

    call = responses.calls[0]
    assert result == "Summary."
    assert call["model"] == "test-model"
    assert call["max_output_tokens"] == 123
    assert "Preserve the key facts" in call["instructions"]
    assert "max_sentences: 2" in call["input"]
    assert "Input text for summary." in call["input"]


def test_llm_client_passes_timeout_retries_and_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)
            self.responses = FakeResponses()

    monkeypatch.setattr(client_module, "AsyncOpenAI", FakeAsyncOpenAI)
    llm_client = OpenAILLMClient(make_settings())

    asyncio.run(llm_client.summarize("Input text for summary.", 2))

    assert created[0]["timeout"] == 7
    assert created[0]["max_retries"] == 4
    assert created[0]["base_url"] == "https://example.test/v1"
    assert created[0]["api_key"] == "test-key"


def test_llm_client_omits_empty_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    created = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)
            self.responses = FakeResponses()

    monkeypatch.setattr(client_module, "AsyncOpenAI", FakeAsyncOpenAI)
    llm_client = OpenAILLMClient(make_settings(openai_base_url=""))

    asyncio.run(llm_client.summarize("Input text for summary.", 2))

    assert "base_url" not in created[0]


def test_llm_client_does_not_call_sdk_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(**kwargs):
        raise AssertionError("SDK should not be created")

    monkeypatch.setattr(client_module, "AsyncOpenAI", fail_if_called)
    llm_client = OpenAILLMClient(make_settings(openai_api_key=None))

    with pytest.raises(LLMConfigurationError):
        asyncio.run(llm_client.summarize("Input text for summary.", 2))


def test_llm_client_empty_output_text_is_invalid_response() -> None:
    responses = FakeResponses(result=SimpleNamespace(output_text=" ", id="resp_123"))
    llm_client = OpenAILLMClient(make_settings(), sdk_client=FakeSDKClient(responses))

    with pytest.raises(LLMInvalidResponseError):
        asyncio.run(llm_client.summarize("Input text for summary.", 2))


@pytest.mark.parametrize(
    ("sdk_error", "expected_error"),
    [
        (lambda: APITimeoutError(request=_request()), LLMTemporaryError),
        (
            lambda: APIConnectionError(message="connect", request=_request()),
            LLMTemporaryError,
        ),
        (
            lambda: AuthenticationError(
                "auth",
                response=_response(401),
                body=None,
            ),
            LLMConfigurationError,
        ),
        (
            lambda: PermissionDeniedError(
                "denied",
                response=_response(403),
                body=None,
            ),
            LLMConfigurationError,
        ),
        (
            lambda: RateLimitError("rate", response=_response(429), body=None),
            LLMTemporaryError,
        ),
        (
            lambda: InternalServerError(
                "server",
                response=_response(500),
                body=None,
            ),
            LLMTemporaryError,
        ),
        (lambda: OpenAIError("boom"), LLMUnexpectedError),
    ],
)
def test_llm_client_maps_sdk_errors(sdk_error, expected_error) -> None:
    responses = FakeResponses(exc=sdk_error())
    llm_client = OpenAILLMClient(make_settings(), sdk_client=FakeSDKClient(responses))

    with pytest.raises(expected_error):
        asyncio.run(llm_client.summarize("Input text for summary.", 2))


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://example.test/v1/responses")


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_request())
