"""Timestamp normalization.

GridShift stores every observation in UTC and keeps the original timezone as provenance.
Naive timestamps are rejected unless the caller supplies an IANA timezone, because
guessing a zone would silently change what an hour means.

Daylight-saving transitions are handled explicitly:

* An **ambiguous** local time (the repeated hour when clocks go back) is resolved by
  occurrence order, so both 01:00 local hours survive as distinct UTC instants.
* A **nonexistent** local time (the skipped hour when clocks go forward) is rejected,
  because no real instant corresponds to it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "AmbiguousLocalTime",
    "NonexistentLocalTime",
    "TimezoneResolutionError",
    "classify_local_time",
    "format_offset",
    "parse_timestamp",
    "resolve_zone",
]


class TimezoneResolutionError(ValueError):
    """Raised when a timestamp cannot be resolved to an unambiguous UTC instant."""


class AmbiguousLocalTime(TimezoneResolutionError):
    """The local time occurs twice; the caller must choose an occurrence."""


class NonexistentLocalTime(TimezoneResolutionError):
    """The local time was skipped by a daylight-saving transition."""


def resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimezoneResolutionError(
            f"Unknown timezone {name!r}. Use an IANA name such as 'America/Los_Angeles' "
            "or 'Europe/London'."
        ) from exc


def format_offset(moment: datetime) -> str:
    """Render a datetime's UTC offset as the original-timezone provenance label."""
    offset = moment.utcoffset()
    if offset is None:
        raise TimezoneResolutionError("Timestamp has no UTC offset.")
    total_minutes = int(offset.total_seconds() // 60)
    if total_minutes == 0:
        return "UTC"
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def classify_local_time(naive: datetime, zone: ZoneInfo) -> str:
    """Return 'unambiguous', 'ambiguous', or 'nonexistent' for a naive local time."""
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() == second.utcoffset():
        return "unambiguous"
    round_tripped = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    return "ambiguous" if round_tripped == naive else "nonexistent"


def parse_timestamp(
    raw: str,
    *,
    timezone_name: str | None = None,
    fold: int = 0,
) -> tuple[datetime, str]:
    """Parse a timestamp into ``(utc_datetime, original_timezone_label)``.

    Args:
        raw: ISO 8601 timestamp, with or without a UTC offset.
        timezone_name: IANA zone, required when ``raw`` carries no offset.
        fold: Which occurrence of an ambiguous local time to use (0 or 1).
    """
    text = (raw or "").strip()
    if not text:
        raise TimezoneResolutionError("Timestamp is empty.")

    normalized = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TimezoneResolutionError(
            f"Could not parse timestamp {raw!r}. Use ISO 8601, for example "
            "'2026-09-16T15:00:00Z' or '2026-09-16T08:00:00-07:00'."
        ) from exc

    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC), format_offset(parsed)

    if not timezone_name:
        raise TimezoneResolutionError(
            f"Timestamp {raw!r} has no UTC offset and no timezone was supplied. "
            "Add an offset, or provide a 'timezone' column with an IANA name."
        )

    zone = resolve_zone(timezone_name)
    kind = classify_local_time(parsed, zone)

    if kind == "nonexistent":
        raise NonexistentLocalTime(
            f"Local time {raw!r} does not exist in {timezone_name} because of a "
            "daylight-saving transition."
        )
    if kind == "ambiguous" and fold not in (0, 1):
        raise AmbiguousLocalTime(
            f"Local time {raw!r} is ambiguous in {timezone_name}; fold must be 0 or 1."
        )

    localized = parsed.replace(tzinfo=zone, fold=fold if kind == "ambiguous" else 0)
    return localized.astimezone(UTC), timezone_name
