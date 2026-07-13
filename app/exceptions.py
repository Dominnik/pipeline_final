"""Application-level exceptions with safe public messages."""


class SummaryServiceError(Exception):
    """Base exception for summary service errors."""


class LLMError(SummaryServiceError):
    """Base exception for controlled LLM errors."""


class LLMConfigurationError(LLMError):
    """LLM is unavailable because configuration or credentials are invalid."""


class LLMTemporaryError(LLMError):
    """LLM request failed because of a temporary provider problem."""


class LLMInvalidResponseError(LLMError):
    """LLM response is missing, blank, or otherwise unusable."""


class LLMUnexpectedError(LLMError):
    """Unexpected SDK error during LLM processing."""


class ServiceUnavailableError(SummaryServiceError):
    """The summarization service cannot produce a response."""
