import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas import SummarizeRequest


def test_valid_text_is_accepted() -> None:
    request = SummarizeRequest(text="This is a valid text for summarization.")

    assert request.text == "This is a valid text for summarization."
    assert request.max_sentences == 3


@pytest.mark.parametrize(
    "text",
    [
        "",
        "                    ",
        "Too short",
    ],
)
def test_invalid_text_is_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        SummarizeRequest(text=text)


def test_too_long_text_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_TEXT_LENGTH", "30")
    get_settings.cache_clear()

    try:
        with pytest.raises(ValidationError):
            SummarizeRequest(text="x" * 31)
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("max_sentences", [0, 11])
def test_invalid_max_sentences_is_rejected(max_sentences: int) -> None:
    with pytest.raises(ValidationError):
        SummarizeRequest(
            text="This is a valid text for summarization.",
            max_sentences=max_sentences,
        )


@pytest.mark.parametrize("max_sentences", [1, 10])
def test_boundary_max_sentences_values_are_accepted(max_sentences: int) -> None:
    request = SummarizeRequest(
        text="This is a valid text for summarization.",
        max_sentences=max_sentences,
    )

    assert request.max_sentences == max_sentences
