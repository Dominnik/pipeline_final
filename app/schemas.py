from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings


class SummarySource(str, Enum):
    llm = "llm"
    fallback = "fallback"


class HealthStatus(str, Enum):
    ok = "ok"
    degraded = "degraded"


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=20)
    max_sentences: int = Field(default=3, ge=1, le=10)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")

        max_text_length = get_settings().max_text_length
        if len(value) > max_text_length:
            raise ValueError(
                f"text length must be less than or equal to {max_text_length}"
            )

        return value


class SummarizeResponse(BaseModel):
    summary: str
    source: SummarySource
    cached: bool
    degraded: bool
    request_id: str


class HealthResponse(BaseModel):
    status: HealthStatus
    app_env: str
    llm_configured: bool
