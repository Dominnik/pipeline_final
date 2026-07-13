import asyncio
import re

import pytest

from app.cache import CachedSummary, TTLCache, build_cache_key
from app.schemas import SummarySource


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def cached_summary(value: str = "Summary.") -> CachedSummary:
    return CachedSummary(
        summary=value,
        source=SummarySource.llm,
        degraded=False,
    )


def test_set_and_get_before_ttl_expires() -> None:
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, max_size=3, clock=clock)

    asyncio.run(cache.set("key", cached_summary()))

    assert asyncio.run(cache.get("key")) == cached_summary()


def test_unknown_key_returns_none() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=3)

    assert asyncio.run(cache.get("missing")) is None


def test_entry_expires_after_ttl() -> None:
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, max_size=3, clock=clock)

    asyncio.run(cache.set("key", cached_summary()))
    clock.advance(10)

    assert asyncio.run(cache.get("key")) is None


def test_expired_entry_is_removed() -> None:
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, max_size=3, clock=clock)

    asyncio.run(cache.set("key", cached_summary()))
    clock.advance(11)
    asyncio.run(cache.get("key"))

    assert asyncio.run(cache.size()) == 0


def test_repeated_set_updates_value() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=3)

    asyncio.run(cache.set("key", cached_summary("Old.")))
    asyncio.run(cache.set("key", cached_summary("New.")))

    assert asyncio.run(cache.get("key")) == cached_summary("New.")


def test_repeated_set_refreshes_ttl() -> None:
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=10, max_size=3, clock=clock)

    asyncio.run(cache.set("key", cached_summary("Old.")))
    clock.advance(9)
    asyncio.run(cache.set("key", cached_summary("New.")))
    clock.advance(9)

    assert asyncio.run(cache.get("key")) == cached_summary("New.")


def test_max_size_evicts_oldest_entry() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=2)

    asyncio.run(cache.set("first", cached_summary("First.")))
    asyncio.run(cache.set("second", cached_summary("Second.")))
    asyncio.run(cache.set("third", cached_summary("Third.")))

    assert asyncio.run(cache.get("first")) is None
    assert asyncio.run(cache.get("second")) == cached_summary("Second.")
    assert asyncio.run(cache.get("third")) == cached_summary("Third.")


def test_size_never_exceeds_max_size() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=2)

    asyncio.run(cache.set("first", cached_summary("First.")))
    asyncio.run(cache.set("second", cached_summary("Second.")))
    asyncio.run(cache.set("third", cached_summary("Third.")))

    assert asyncio.run(cache.size()) == 2


def test_clear_removes_entries() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=3)

    asyncio.run(cache.set("key", cached_summary()))
    asyncio.run(cache.clear())

    assert asyncio.run(cache.get("key")) is None


def test_concurrent_get_set_keeps_cache_consistent() -> None:
    cache = TTLCache(ttl_seconds=10, max_size=5)

    async def worker(index: int) -> None:
        await cache.set(f"key-{index}", cached_summary(f"Summary {index}."))
        await cache.get(f"key-{index}")

    async def run_workers() -> int:
        await asyncio.gather(*(worker(index) for index in range(20)))
        return await cache.size()

    assert asyncio.run(run_workers()) <= 5


def test_same_inputs_produce_same_cache_key() -> None:
    first = _key(text="Text with facts.")
    second = _key(text="Text with facts.")

    assert first == second


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (" Text with facts. ", "Text with facts."),
        ("Text   with\nfacts.", "Text with facts."),
    ],
)
def test_extra_whitespace_does_not_change_cache_key(left: str, right: str) -> None:
    assert _key(text=left) == _key(text=right)


@pytest.mark.parametrize(
    ("kwargs", "other_kwargs"),
    [
        ({"text": "Text with facts."}, {"text": "text with facts."}),
        ({"text": "Text with facts."}, {"text": "Text with facts!"}),
        ({"max_sentences": 2}, {"max_sentences": 3}),
        ({"model": "model-a"}, {"model": "model-b"}),
        ({"prompt_version": "v1"}, {"prompt_version": "v2"}),
        ({"max_output_tokens": 100}, {"max_output_tokens": 200}),
    ],
)
def test_result_affecting_inputs_change_cache_key(
    kwargs: dict,
    other_kwargs: dict,
) -> None:
    assert _key(**kwargs) != _key(**other_kwargs)


def test_cache_key_is_sha256_and_does_not_expose_text() -> None:
    key = _key(text="Sensitive source text.")

    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert "Sensitive" not in key
    assert "source" not in key


def _key(**kwargs) -> str:
    values = {
        "text": "Text with facts.",
        "max_sentences": 2,
        "model": "test-model",
        "prompt_version": "v1",
        "max_output_tokens": 128,
    }
    values.update(kwargs)
    return build_cache_key(**values)
