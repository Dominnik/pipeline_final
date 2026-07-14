import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Optional

from app.schemas import SummarySource


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedSummary:
    summary: str
    source: SummarySource
    degraded: bool


@dataclass(frozen=True)
class _CacheEntry:
    value: CachedSummary
    expires_at: float


class TTLCache:
    def __init__(
        self,
        ttl_seconds: int,
        max_size: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than 0")
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")

        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._clock = clock
        self._items: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = RLock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    async def get(self, key: str) -> Optional[CachedSummary]:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None

            now = self._clock()
            if entry.expires_at <= now:
                del self._items[key]
                logger.info(
                    "Cache entry expired",
                    extra={
                        "event": "cache_expired",
                        "cache_key_prefix": cache_key_prefix(key),
                        "cache_size": len(self._items),
                    },
                )
                return None

            return entry.value

    async def set(self, key: str, value: CachedSummary) -> None:
        with self._lock:
            now = self._clock()
            self._remove_expired(now)

            if key in self._items:
                del self._items[key]

            self._items[key] = _CacheEntry(
                value=value,
                expires_at=now + self._ttl_seconds,
            )

            while len(self._items) > self._max_size:
                evicted_key, _ = self._items.popitem(last=False)
                logger.info(
                    "Cache entry evicted",
                    extra={
                        "event": "cache_evicted",
                        "cache_key_prefix": cache_key_prefix(evicted_key),
                        "cache_size": len(self._items),
                    },
                )

            logger.info(
                "Cache entry stored",
                extra={
                    "event": "cache_set",
                    "cache_key_prefix": cache_key_prefix(key),
                    "cache_ttl_seconds": self._ttl_seconds,
                    "cache_size": len(self._items),
                },
            )

    async def clear(self) -> None:
        with self._lock:
            self._items.clear()

    async def size(self) -> int:
        with self._lock:
            self._remove_expired(self._clock())
            return len(self._items)

    def _remove_expired(self, now: float) -> None:
        expired_keys = [
            key for key, entry in self._items.items() if entry.expires_at <= now
        ]
        for key in expired_keys:
            del self._items[key]
            logger.info(
                "Cache entry expired",
                extra={
                    "event": "cache_expired",
                    "cache_key_prefix": cache_key_prefix(key),
                    "cache_size": len(self._items),
                },
            )


def build_cache_key(
    *,
    text: str,
    max_sentences: int,
    model: str,
    prompt_version: str,
    max_output_tokens: int,
) -> str:
    payload = {
        "text": _normalize_text_for_key(text),
        "max_sentences": max_sentences,
        "model": model,
        "prompt_version": prompt_version,
        "max_output_tokens": max_output_tokens,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cache_key_prefix(key: str) -> str:
    return key[:12]


def _normalize_text_for_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
