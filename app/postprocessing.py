import re
from typing import Optional

from app.exceptions import LLMInvalidResponseError


FENCE_PATTERN = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*(.*?)\s*```$", re.DOTALL)
PREFIX_PATTERN = re.compile(
    r"^(Summary:|Резюме:|Краткое содержание:)\s*", re.IGNORECASE
)


def clean_model_output(value: Optional[str]) -> str:
    if value is None:
        raise LLMInvalidResponseError("empty model response")

    result = value.strip()
    fence_match = FENCE_PATTERN.match(result)
    if fence_match:
        result = fence_match.group(1).strip()

    result = PREFIX_PATTERN.sub("", result, count=1).strip()
    result = _normalize_whitespace(result)

    if not result:
        raise LLMInvalidResponseError("empty model response")

    return result


def _normalize_whitespace(value: str) -> str:
    normalized_lines = []

    for line in value.splitlines():
        normalized_line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if not normalized_line:
            continue
        normalized_lines.append(normalized_line)

    return "\n".join(normalized_lines).strip()
