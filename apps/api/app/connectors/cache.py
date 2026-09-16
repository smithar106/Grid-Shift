"""A small in-process TTL cache for external API responses.

The PRD requires caching external responses. It also requires that a re-run be
reproducible, which is why the cache stores the *response body* rather than the parsed
objects: the archived payload is the evidence of what the upstream actually said.

This is deliberately in-process. A shared cache (Redis) is only worth adding once more
than one API replica serves traffic.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

__all__ = ["ResponseCache", "cache_key"]


def cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    """Stable key for a request, independent of dict ordering."""
    digest = hashlib.sha256()
    digest.update(url.encode())
    for name, value in sorted((params or {}).items()):
        digest.update(f"|{name}={value}".encode())
    return digest.hexdigest()


@dataclass(slots=True)
class _Entry:
    payload: Any
    stored_at: float


class ResponseCache:
    """A bounded TTL cache. Evicts the oldest entry when full."""

    def __init__(self, ttl_seconds: float, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, _Entry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.stored_at > self._ttl:
            del self._entries[key]
            return None
        return entry.payload

    def set(self, key: str, payload: Any) -> None:
        if len(self._entries) >= self._max_entries:
            oldest = min(self._entries, key=lambda name: self._entries[name].stored_at)
            del self._entries[oldest]
        self._entries[key] = _Entry(payload=payload, stored_at=time.monotonic())

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
