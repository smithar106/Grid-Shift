"""Custom column types.

SQLite does not preserve timezone information, so a ``DateTime(timezone=True)`` column
comes back naive on SQLite but aware on PostgreSQL. GridShift's contracts require
timezone-aware UTC everywhere, so timestamps go through ``UtcDateTime`` and are
normalized on the way in and on the way out.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ["UtcDateTime", "utcnow"]


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC datetime, on every backend."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected a datetime, got {type(value).__name__}.")
        if value.tzinfo is None:
            raise ValueError(
                "Refusing to store a naive datetime. Timestamps must be timezone-aware."
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected a datetime, got {type(value).__name__}.")
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
