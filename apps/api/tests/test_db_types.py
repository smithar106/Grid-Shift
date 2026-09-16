"""Timezone handling in persistence.

SQLite drops timezone information, so without the custom column type every timestamp read
back would be naive and would silently shift the meaning of an hour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import Base
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


# --- Engine and session factory -----------------------------------------------------
# The API's own tests override the session dependency, so the engine wiring that
# production actually uses is exercised here instead.


def test_engine_uses_the_configured_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.services.db import get_engine, reset_engine_cache

    database = tmp_path / "audit.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    reset_engine_cache()

    try:
        engine = get_engine()
        assert str(engine.url).endswith("audit.db")

        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            names = {
                row[0]
                for row in connection.exec_driver_sql(
                    "select name from sqlite_master where type='table'"
                )
            }
        assert {"facilities", "datasets", "scenarios"} <= names
    finally:
        reset_engine_cache()
        get_settings.cache_clear()


def test_session_factory_round_trips_a_facility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.services.db import get_engine, get_session_factory, reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'round.db'}")
    get_settings.cache_clear()
    reset_engine_cache()

    try:
        Base.metadata.create_all(get_engine())
        session = get_session_factory()()
        try:
            session.add(
                Facility(
                    name="Engine Check",
                    location_id="facility_engine",
                    timezone="UTC",
                    capacity_mw=12.0,
                )
            )
            session.commit()
            stored = session.query(Facility).one()
            assert stored.location_id == "facility_engine"
            assert stored.created_at.utcoffset() == timedelta(0)
        finally:
            session.close()
    finally:
        reset_engine_cache()
        get_settings.cache_clear()


def test_sqlite_engine_allows_cross_thread_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FastAPI runs sync endpoints in a threadpool; SQLite would otherwise refuse."""
    import threading

    from app.config import get_settings
    from app.services.db import get_engine, reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'threads.db'}")
    get_settings.cache_clear()
    reset_engine_cache()

    try:
        engine = get_engine()
        Base.metadata.create_all(engine)
        errors: list[Exception] = []

        def worker() -> None:
            try:
                with engine.connect() as connection:
                    connection.exec_driver_sql("select 1")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert errors == []
    finally:
        reset_engine_cache()
        get_settings.cache_clear()


def test_get_session_closes_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.db import get_session

    closed: list[bool] = []

    class FakeSession:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("app.services.db.get_session_factory", lambda: lambda: FakeSession())

    generator = get_session()
    session = next(generator)
    assert isinstance(session, FakeSession)

    with pytest.raises(StopIteration):
        next(generator)
    assert closed == [True]


def test_sqlite_foreign_keys_are_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite disables foreign keys by default, so ON DELETE CASCADE would silently not
    fire in development while working in production."""

    from app.config import get_settings
    from app.services.db import get_engine, reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fk.db'}")
    get_settings.cache_clear()
    reset_engine_cache()

    try:
        engine = get_engine()
        with engine.connect() as connection:
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        assert enabled == 1
    finally:
        reset_engine_cache()
        get_settings.cache_clear()


def test_deleting_a_scenario_cascades_to_its_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercises the real engine rather than the overridden test session."""
    from app.config import get_settings
    from app.models.scenario import OptimizationResultRecord, Scenario, ScenarioWorkload
    from app.services.db import get_engine, get_session_factory, reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cascade.db'}")
    get_settings.cache_clear()
    reset_engine_cache()

    try:
        engine = get_engine()
        Base.metadata.create_all(engine)
        session = get_session_factory()()

        facility = Facility(
            name="Cascade", location_id="facility_cascade", timezone="UTC", capacity_mw=10.0
        )
        session.add(facility)
        session.flush()
        scenario = Scenario(
            facility_id=facility.id,
            name="Cascade scenario",
            objective="cost",
            dataset_ids=[],
            workloads=[
                ScenarioWorkload(
                    job_id="a", energy_mwh=1.0, release_hour=0, deadline_hour=1, max_mw=1.0
                )
            ],
        )
        session.add(scenario)
        session.commit()

        session.add(OptimizationResultRecord(scenario_id=scenario.id, solver_status="optimal"))
        session.commit()

        scenario_id = scenario.id
        session.delete(scenario)
        session.commit()
        session.expire_all()

        from sqlalchemy import select

        assert (
            session.scalars(
                select(ScenarioWorkload).where(ScenarioWorkload.scenario_id == scenario_id)
            ).all()
            == []
        )
        assert (
            session.scalars(
                select(OptimizationResultRecord).where(
                    OptimizationResultRecord.scenario_id == scenario_id
                )
            ).all()
            == []
        )
        session.close()
    finally:
        reset_engine_cache()
        get_settings.cache_clear()
