import logging
import time
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
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


PROMPT_VERSION = "v1"

logger = logging.getLogger(__name__)


class OpenAILLMClient:
    def __init__(
        self,
        settings: Settings,
        sdk_client: Optional[Any] = None,
    ) -> None:
        self._settings = settings
        self._sdk_client = sdk_client

    async def summarize(self, text: str, max_sentences: int) -> str:
        system_prompt, user_prompt = build_prompt(text, max_sentences)
        prompt_length = len(system_prompt) + len(user_prompt)
        logger.info(
            "Prompt created",
            extra={
                "event": "prompt_created",
                "prompt_version": PROMPT_VERSION,
                "prompt_length": prompt_length,
            },
        )

        started_at = time.monotonic()
        try:
            client = self._get_client()
        except LLMConfigurationError as exc:
            self._log_llm_failure(exc, started_at)
            raise

        try:
            logger.info(
                "LLM request started",
                extra={
                    "event": "llm_request_started",
                    "model": self._settings.openai_model,
                    "prompt_version": PROMPT_VERSION,
                },
            )
            response = await client.responses.create(
                model=self._settings.openai_model,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=self._settings.llm_max_output_tokens,
            )
        except (AuthenticationError, PermissionDeniedError) as exc:
            self._log_llm_failure(exc, started_at)
            raise LLMConfigurationError("llm configuration error") from exc
        except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
            self._log_llm_failure(exc, started_at)
            raise LLMTemporaryError("temporary llm error") from exc
        except InternalServerError as exc:
            self._log_llm_failure(exc, started_at)
            raise LLMTemporaryError("temporary llm error") from exc
        except APIStatusError as exc:
            self._log_llm_failure(exc, started_at)
            if exc.status_code in {401, 403}:
                raise LLMConfigurationError("llm configuration error") from exc
            if exc.status_code == 429 or exc.status_code >= 500:
                raise LLMTemporaryError("temporary llm error") from exc
            raise LLMUnexpectedError("unexpected llm status error") from exc
        except OpenAIError as exc:
            self._log_llm_failure(exc, started_at)
            raise LLMUnexpectedError("unexpected llm error") from exc

        output_text = getattr(response, "output_text", None)
        if output_text is None or not output_text.strip():
            self._log_llm_failure(
                LLMInvalidResponseError("empty model response"), started_at
            )
            raise LLMInvalidResponseError("empty model response")

        duration_ms = _duration_ms(started_at)
        logger.info(
            "LLM response received",
            extra={
                "event": "llm_response_received",
                "response_length": len(output_text),
                "duration_ms": duration_ms,
                "provider_request_id": getattr(response, "id", None),
            },
        )

        return output_text

    def _get_client(self) -> Any:
        if self._sdk_client is not None:
            return self._sdk_client

        if not self._settings.llm_configured:
            raise LLMConfigurationError("llm api key is not configured")

        api_key = self._settings.openai_api_key
        if api_key is None:
            raise LLMConfigurationError("llm api key is not configured")

        kwargs: dict[str, Any] = {
            "api_key": api_key.get_secret_value(),
            "timeout": self._settings.llm_timeout_seconds,
            "max_retries": self._settings.llm_max_retries,
        }

        base_url = self._settings.openai_base_url.strip()
        if base_url:
            kwargs["base_url"] = base_url

        self._sdk_client = AsyncOpenAI(**kwargs)
        return self._sdk_client

    def _log_llm_failure(self, exc: Exception, started_at: float) -> None:
        logger.warning(
            "LLM request failed",
            extra={
                "event": "llm_request_failed",
                "error_type": exc.__class__.__name__,
                "provider_status_code": getattr(exc, "status_code", None),
                "duration_ms": _duration_ms(started_at),
            },
        )


def build_prompt(text: str, max_sentences: int) -> tuple[str, str]:
    system_prompt = (
        "Briefly summarize the provided text. Preserve the key facts. "
        "Do not add information that is not present in the source text. "
        "Return only the final summary. Do not add headings, explanations, "
        "or service comments. Use the language of the source text. "
        "Respect the requested max_sentences limit."
    )
    user_prompt = f"max_sentences: {max_sentences}\n\n" "Text to summarize:\n" f"{text}"
    return system_prompt, user_prompt


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)
