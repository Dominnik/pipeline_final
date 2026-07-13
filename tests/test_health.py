import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_without_api_key_returns_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "app_env": "test",
        "llm_configured": False,
    }
    assert "test-api-key" not in response.text


def test_health_with_api_key_returns_ok_without_leaking_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "test-api-key"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    get_settings.cache_clear()

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_env": "test",
        "llm_configured": True,
    }
    assert api_key not in response.text
