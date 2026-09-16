from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.services.timeutil import (
    AmbiguousLocalTime,
    NonexistentLocalTime,
    TimezoneResolutionError,
    classify_local_time,
    format_offset,
    parse_timestamp,
    resolve_zone,
)


def test_parses_utc_zulu_suffix() -> None:
    moment, label = parse_timestamp("2026-09-16T15:00:00Z")
    assert moment == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
    assert label == "UTC"


def test_preserves_original_offset_and_converts_to_utc() -> None:
    moment, label = parse_timestamp("2026-09-16T08:00:00-07:00")
    assert moment == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
    assert label == "-07:00"


def test_localizes_naive_timestamp_with_iana_zone() -> None:
    moment, label = parse_timestamp("2026-09-16T08:00:00", timezone_name="America/Los_Angeles")
    assert moment == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
    assert label == "America/Los_Angeles"


def test_rejects_naive_timestamp_without_timezone() -> None:
    with pytest.raises(TimezoneResolutionError, match="no UTC offset"):
        parse_timestamp("2026-09-16T08:00:00")


def test_rejects_unknown_timezone() -> None:
    with pytest.raises(TimezoneResolutionError, match="Unknown timezone"):
        resolve_zone("Mars/Olympus_Mons")


def test_rejects_unparseable_timestamp() -> None:
    with pytest.raises(TimezoneResolutionError, match="Could not parse"):
        parse_timestamp("16/09/2026 08:00")


def test_rejects_empty_timestamp() -> None:
    with pytest.raises(TimezoneResolutionError, match="empty"):
        parse_timestamp("   ")


# --- Daylight saving ---------------------------------------------------------------
# US DST 2026: clocks go forward on 8 March and back on 1 November.


def test_fall_back_hour_is_ambiguous_and_resolved_by_fold() -> None:
    zone = resolve_zone("America/Los_Angeles")
    naive = datetime(2026, 11, 1, 1, 30)

    assert classify_local_time(naive, zone) == "ambiguous"

    first, _ = parse_timestamp("2026-11-01T01:30:00", timezone_name="America/Los_Angeles", fold=0)
    second, _ = parse_timestamp("2026-11-01T01:30:00", timezone_name="America/Los_Angeles", fold=1)

    assert first == datetime(2026, 11, 1, 8, 30, tzinfo=UTC)
    assert second == datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
    assert first != second


def test_spring_forward_hour_does_not_exist() -> None:
    zone = resolve_zone("America/Los_Angeles")
    assert classify_local_time(datetime(2026, 3, 8, 2, 30), zone) == "nonexistent"

    with pytest.raises(NonexistentLocalTime, match="does not exist"):
        parse_timestamp("2026-03-08T02:30:00", timezone_name="America/Los_Angeles")


def test_unambiguous_local_time() -> None:
    zone = resolve_zone("America/Los_Angeles")
    assert classify_local_time(datetime(2026, 9, 16, 8, 0), zone) == "unambiguous"


def test_ambiguous_fold_out_of_range_is_rejected() -> None:
    with pytest.raises(AmbiguousLocalTime, match="fold must be 0 or 1"):
        parse_timestamp("2026-11-01T01:30:00", timezone_name="America/Los_Angeles", fold=7)


def test_format_offset_variants() -> None:
    assert format_offset(datetime(2026, 9, 16, 15, 0, tzinfo=UTC)) == "UTC"
    assert (
        format_offset(datetime(2026, 9, 16, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))))
        == "+05:30"
    )
    assert (
        format_offset(datetime(2026, 9, 16, 15, 0, tzinfo=timezone(timedelta(hours=-7))))
        == "-07:00"
    )
