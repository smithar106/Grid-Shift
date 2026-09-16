"""Weather endpoint.

The connector is stubbed so these tests describe the endpoint's contract: what it returns,
and that it refuses to pretend weather affects the optimization.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.connectors.base import ConnectorResult, UpstreamUnavailable
from app.main import create_app
from app.routers.weather import get_connector
from app.schemas.enums import DataSource, DataStatus, Metric, Unit
from app.schemas.observations import Observation

START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


class StubConnector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def fetch(self, **_: object) -> ConnectorResult:
        if self.fail:
            raise UpstreamUnavailable("Open-Meteo is unavailable.")
        observations = []
        for hour in range(3):
            for metric, unit, value in (
                (Metric.TEMPERATURE, Unit.CELSIUS, 14.0 + hour),
                (Metric.RELATIVE_HUMIDITY, Unit.PERCENT, 80.0 - hour),
            ):
                observations.append(
                    Observation(
                        timestamp_utc=START + timedelta(hours=hour),
                        location_id="facility_001",
                        metric=metric,
                        value=value,
                        unit=unit,
                        source=DataSource.OPEN_METEO,
                        data_status=DataStatus.RETRIEVED,
                        original_timestamp="",
                        original_timezone="UTC",
                        original_value=value,
                        original_unit=unit,
                        retrieved_at=START,
                    )
                )
        return ConnectorResult(
            source=DataSource.OPEN_METEO,
            data_status=DataStatus.RETRIEVED,
            retrieved_at=START,
            location_id="facility_001",
            observations=tuple(observations),
        )


@pytest.fixture
def weather_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_connector] = lambda: StubConnector()
    client = TestClient(app)
    yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


@pytest.fixture
def failing_weather_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_connector] = lambda: StubConnector(fail=True)
    client = TestClient(app)
    yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


def test_weather_returns_hourly_points(weather_client: TestClient) -> None:
    response = weather_client.get(
        "/api/v1/weather", params={"latitude": 37.77, "longitude": -122.42}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["points"]) == 3
    assert body["points"][0]["temperature_c"] == 14.0
    assert body["points"][0]["relative_humidity_pct"] == 80.0
    assert body["source"] == "open_meteo"
    assert body["data_status"] == "retrieved"
    assert "Open-Meteo" in body["attribution"]


def test_weather_declares_it_does_not_affect_the_objective(weather_client: TestClient) -> None:
    """Weather is context. Implying it drives the schedule would overstate the model."""
    body = weather_client.get("/api/v1/weather", params={"latitude": 1.0, "longitude": 2.0}).json()
    assert body["affects_objective"] is False


def test_weather_requires_valid_coordinates(weather_client: TestClient) -> None:
    assert (
        weather_client.get("/api/v1/weather", params={"latitude": 999, "longitude": 0}).status_code
        == 422
    )
    assert weather_client.get("/api/v1/weather").status_code == 422


def test_upstream_failure_returns_502_without_fabricating_weather(
    failing_weather_client: TestClient,
) -> None:
    response = failing_weather_client.get(
        "/api/v1/weather", params={"latitude": 1.0, "longitude": 2.0}
    )

    assert response.status_code == 502
    assert response.json()["error"] == "upstream_unavailable"
    assert "unavailable" in response.json()["message"]
