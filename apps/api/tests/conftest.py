"""Shared API test fixtures.

Tests run against an in-memory SQLite database created from the models, with the session
dependency overridden. The schema is built by SQLAlchemy rather than by running Alembic, so
these tests exercise the ORM contracts; the migration itself is verified separately.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.models import Base
from app.services.db import get_session

START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    # A single shared connection keeps the in-memory database alive for the whole test.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def build_csv(rows: list[dict[str, str]], columns: list[str] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def hourly_rows(
    metric: str,
    unit: str,
    values: list[float],
    *,
    start: datetime = START,
    location: str | None = None,
) -> list[dict[str, str]]:
    rows = []
    for index, value in enumerate(values):
        row = {
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "metric": metric,
            "value": str(value),
            "unit": unit,
        }
        if location is not None:
            row["location_id"] = location
        rows.append(row)
    return rows


def sample_dataset_csv(hours: int = 24) -> str:
    """A complete three-metric hourly file.

    Prices and carbon are high early and low late, so the earliest-feasible baseline (which
    front-loads work) is genuinely suboptimal. A flat or front-loaded price curve would
    make the baseline accidentally optimal and hide any bug in the comparison.
    """
    prices = [90.0 if hour < 12 else 40.0 for hour in range(hours)]
    carbons = [0.6 if hour < 12 else 0.2 for hour in range(hours)]
    loads = [12.0] * hours
    rows = [
        *hourly_rows("electricity_price", "USD/MWh", prices),
        *hourly_rows("carbon_intensity", "tCO2e/MWh", carbons),
        *hourly_rows("facility_load", "MWh", loads),
    ]
    return build_csv(rows)


def create_facility(client: TestClient, **overrides: object) -> dict:
    payload = {
        "name": "Test Facility",
        "location_id": "facility_001",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "timezone": "America/Los_Angeles",
        "capacity_mw": 40.0,
    }
    payload.update(overrides)
    response = client.post("/api/v1/facilities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upload_dataset(client: TestClient, *, csv_text: str, **form: object) -> dict:
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("sample.csv", csv_text.encode(), "text/csv")},
        data={key: str(value) for key, value in form.items()},
    )
    return {"status_code": response.status_code, "body": response.json()}
