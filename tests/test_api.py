import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_summarization_service, get_ttl_cache
from app.cache import TTLCache
from app.core.config import Settings, get_settings
from app.exceptions import LLMInvalidResponseError, LLMTemporaryError
from app.main import app
from app.services.summarization import SummarizationService


VALID_TEXT = "This is a valid text for summarization. It has enough detail."


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


@pytest.fixture(autouse=True)
def reset_app_state() -> None:
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_ttl_cache.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_ttl_cache.cache_clear()


def test_summarize_successful_fake_llm_returns_200() -> None:
    app.dependency_overrides[get_summarization_service] = lambda: SummarizationService(
        FakeLLMClient(" Summary: Clean summary. ")
    )

    response = TestClient(app).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["summary"] == "Clean summary."
    assert body["source"] == "llm"
    assert body["degraded"] is False
    assert body["cached"] is False
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_summarize_second_identical_request_uses_cache() -> None:
    llm = FakeLLMClient("Clean summary.")
    service = SummarizationService(
        llm,
        settings=Settings(
            cache_enabled=True,
            cache_ttl_seconds=300,
            cache_max_size=10,
            openai_model="test-model",
            llm_max_output_tokens=128,
        ),
        cache=TTLCache(ttl_seconds=300, max_size=10),
    )
    app.dependency_overrides[get_summarization_service] = lambda: service
    client = TestClient(app)

    first = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )
    second = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )

    first_body = first.json()
    second_body = second.json()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first_body["source"] == "llm"
    assert first_body["cached"] is False
    assert first_body["degraded"] is False
    assert second_body["source"] == "llm"
    assert second_body["cached"] is True
    assert second_body["degraded"] is False
    assert llm.calls == 1
    assert first_body["request_id"] != second_body["request_id"]
    assert first.headers["X-Request-ID"] == first_body["request_id"]
    assert second.headers["X-Request-ID"] == second_body["request_id"]


def test_summarize_changed_max_sentences_is_cache_miss() -> None:
    llm = FakeLLMClient("Clean summary.")
    service = SummarizationService(
        llm,
        settings=Settings(cache_enabled=True),
        cache=TTLCache(ttl_seconds=300, max_size=10),
    )
    app.dependency_overrides[get_summarization_service] = lambda: service
    client = TestClient(app)

    first = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 2},
    )
    second = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert llm.calls == 2


def test_summarize_without_api_key_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    response = TestClient(app).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["source"] == "fallback"
    assert body["degraded"] is True
    assert body["summary"]


def test_summarize_timeout_uses_fallback() -> None:
    app.dependency_overrides[get_summarization_service] = lambda: SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout"))
    )

    response = TestClient(app).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "fallback"


def test_repeated_fallback_requests_are_not_cached() -> None:
    llm = FakeLLMClient(exc=LLMTemporaryError("timeout"))
    service = SummarizationService(
        llm,
        settings=Settings(cache_enabled=True),
        cache=TTLCache(ttl_seconds=300, max_size=10),
    )
    app.dependency_overrides[get_summarization_service] = lambda: service
    client = TestClient(app)

    first = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )
    second = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["source"] == "fallback"
    assert second.json()["source"] == "fallback"
    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert llm.calls == 2


def test_disabled_cache_keeps_repeated_requests_uncached() -> None:
    llm = FakeLLMClient("Clean summary.")
    service = SummarizationService(
        llm,
        settings=Settings(cache_enabled=False),
        cache=TTLCache(ttl_seconds=300, max_size=10),
    )
    app.dependency_overrides[get_summarization_service] = lambda: service
    client = TestClient(app)

    first = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )
    second = client.post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 3},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert llm.calls == 2


def test_summarize_empty_model_response_uses_fallback() -> None:
    app.dependency_overrides[get_summarization_service] = lambda: SummarizationService(
        FakeLLMClient(exc=LLMInvalidResponseError("empty"))
    )

    response = TestClient(app).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "fallback"


def test_summarize_fallback_error_returns_503() -> None:
    def broken_fallback(text: str, max_sentences: int) -> str:
        raise RuntimeError("private fallback failure")

    app.dependency_overrides[get_summarization_service] = lambda: SummarizationService(
        FakeLLMClient(exc=LLMTemporaryError("timeout")),
        fallback=broken_fallback,
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    body = response.json()
    assert response.status_code == 503
    assert body["detail"] == "Сервис суммаризации временно недоступен."
    assert body["request_id"]
    assert "private fallback failure" not in response.text


def test_unexpected_internal_api_error_returns_500() -> None:
    def broken_dependency() -> SummarizationService:
        raise RuntimeError("private stack detail")

    app.dependency_overrides[get_summarization_service] = broken_dependency

    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/summarize",
        json={"text": VALID_TEXT, "max_sentences": 1},
    )

    body = response.json()
    assert response.status_code == 500
    assert body["detail"] == "Внутренняя ошибка сервиса."
    assert "private stack detail" not in response.text
    assert "Traceback" not in response.text
