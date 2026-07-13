import re


FALLBACK_MAX_CHARS = 500


def summarize_locally(text: str, max_sentences: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        raise ValueError("text is empty")

    sentences = _split_sentences(normalized)
    if sentences:
        summary = " ".join(sentences[:max_sentences]).strip()
    else:
        summary = normalized

    summary = _truncate(summary, FALLBACK_MAX_CHARS)
    if not summary:
        raise ValueError("fallback produced empty summary")

    return summary


def _split_sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text)
        if match.group(0).strip()
    ]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    truncated = text[: max_chars - 3].rstrip()
    return f"{truncated}..."
