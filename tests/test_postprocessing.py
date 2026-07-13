import pytest

from app.exceptions import LLMInvalidResponseError
from app.postprocessing import clean_model_output


def test_strips_outer_whitespace() -> None:
    assert clean_model_output("  Summary text. \n") == "Summary text."


def test_normalizes_blank_lines_and_spaces() -> None:
    value = "First   line.\n\n\nSecond\t\tline."

    assert clean_model_output(value) == "First line.\nSecond line."


def test_removes_markdown_fence() -> None:
    assert clean_model_output("```markdown\nSummary text.\n```") == "Summary text."


@pytest.mark.parametrize(
    "value",
    [
        "Summary: Result text.",
        "Резюме: Итоговый текст.",
        "Краткое содержание: Итоговый текст.",
    ],
)
def test_removes_service_prefix(value: str) -> None:
    assert ":" not in clean_model_output(value).split()[0]


def test_preserves_regular_punctuation() -> None:
    assert clean_model_output("Hello, world! Are you ready?") == (
        "Hello, world! Are you ready?"
    )


@pytest.mark.parametrize("value", [None, "", "   \n\t"])
def test_empty_values_are_rejected(value: str) -> None:
    with pytest.raises(LLMInvalidResponseError):
        clean_model_output(value)
