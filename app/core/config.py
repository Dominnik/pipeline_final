from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM Summary Service"
    app_env: str = "local"
    log_level: str = "INFO"

    openai_api_key: Optional[SecretStr] = Field(default=None, repr=False)
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    llm_timeout_seconds: float = Field(default=10.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)

    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=300, gt=0)
    cache_max_size: int = Field(default=1024, gt=0)

    max_text_length: int = Field(default=10_000, gt=0)

    @property
    def llm_configured(self) -> bool:
        if self.openai_api_key is None:
            return False
        return bool(self.openai_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
