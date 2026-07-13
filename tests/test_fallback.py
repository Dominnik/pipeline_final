from app.fallback import summarize_locally


def test_russian_text_with_multiple_sentences() -> None:
    text = "Это первое предложение. Это второе предложение! Это третье?"

    assert summarize_locally(text, max_sentences=2) == (
        "Это первое предложение. Это второе предложение!"
    )


def test_english_text_with_multiple_sentences() -> None:
    text = "First fact. Second fact! Third fact?"

    assert summarize_locally(text, max_sentences=1) == "First fact."


def test_text_without_final_period() -> None:
    text = "This text has no final punctuation but remains usable"

    assert summarize_locally(text, max_sentences=3) == text


def test_normalizes_spaces_and_newlines() -> None:
    text = "First   sentence.\n\nSecond\t sentence."

    assert summarize_locally(text, max_sentences=2) == (
        "First sentence. Second sentence."
    )


def test_limits_max_sentences() -> None:
    text = "One. Two. Three."

    assert summarize_locally(text, max_sentences=2) == "One. Two."


def test_result_is_not_empty_for_valid_text() -> None:
    assert summarize_locally("Useful text without punctuation", max_sentences=3)


def test_long_text_without_sentence_end_is_truncated() -> None:
    result = summarize_locally("x" * 700, max_sentences=3)

    assert len(result) == 500
    assert result.endswith("...")


def test_truncated_text_does_not_end_with_four_dots() -> None:
    text = ("Sentence. " * 80).strip()

    result = summarize_locally(text, max_sentences=80)

    assert result.endswith("...")
    assert not result.endswith("....")
