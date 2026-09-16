"""Timezone handling in persistence.

SQLite drops timezone information, so without the custom column type every timestamp read
back would be naive and would silently shift the meaning of an hour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.facility import Facility
from app.models.types import UtcDateTime


def test_bind_rejects_naive_datetime() -> None:
    column_type = UtcDateTime()
    with pytest.raises(ValueError, match="naive datetime"):
        column_type.process_bind_param(datetime(2026, 9, 16, 12, 0), None)  # type: ignore[arg-type]


def test_bind_converts_other_offsets_to_utc() -> None:
    column_type = UtcDateTime()
    shifted = datetime(2026, 9, 16, 8, 0, tzinfo=timezone(timedelta(hours=-7)))

    result = column_type.process_bind_param(shifted, None)  # type: ignore[arg-type]

    assert result == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)


def test_bind_passes_through_none() -> None:
    assert UtcDateTime().process_bind_param(None, None) is None  # type: ignore[arg-type]


def test_bind_rejects_non_datetime() -> None:
    with pytest.raises(TypeError, match="Expected a datetime"):
        UtcDateTime().process_bind_param("2026-09-16", None)  # type: ignore[arg-type]


def test_result_attaches_utc_to_naive_values() -> None:
    """This is the SQLite case: the driver hands back a naive datetime."""
    result = UtcDateTime().process_result_value(datetime(2026, 9, 16, 12, 0), None)  # type: ignore[arg-type]
    assert result == datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    assert result is not None and result.tzinfo is not None


def test_result_normalizes_aware_values() -> None:
    shifted = datetime(2026, 9, 16, 8, 0, tzinfo=timezone(timedelta(hours=-7)))
    result = UtcDateTime().process_result_value(shifted, None)  # type: ignore[arg-type]
    assert result == datetime(2026, 9, 16, 15, 0, tzinfo=UTC)


def test_round_trip_through_sqlite_keeps_utc(db_session: Session) -> None:
    moment = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    facility = Facility(
        name="Round Trip",
        location_id="facility_rt",
        timezone="America/Los_Angeles",
        capacity_mw=25.0,
    )
    db_session.add(facility)
    db_session.commit()
    db_session.expunge_all()

    loaded = db_session.get(Facility, facility.id)
    assert loaded is not None
    assert loaded.created_at.tzinfo is not None
    assert loaded.created_at.utcoffset() == timedelta(0)
    assert loaded.created_at >= moment - timedelta(minutes=1)
