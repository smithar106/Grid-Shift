"""Open-Meteo connector.

The upstream is mocked, but nothing else is: these tests assert the real normalization,
the real caching behaviour, and — most importantly — that a failing upstream produces an
error rather than a fabricated value.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.connectors.base import UpstreamUnavailable
from app.connectors.open_meteo import ATTRIBUTION, OpenMeteoConnector
from app.schemas.enums import DataSource, DataStatus, Metric, Unit

BASE_URL = "https://api.open-meteo.com/v1/forecast"

PAYLOAD = {
    "latitude": 37.77,
    "longitude": -122.42,
    "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "relative_humidity_2m": "%"},
    "hourly": {
        "time": ["2026-09-16T00:00", "2026-09-16T01:00", "2026-09-16T02:00"],
        "temperature_2m": [14.2, 13.8, 13.1],
        "relative_humidity_2m": [81, 84, 86],
    },
}


def make_connector(**kwargs: object) -> OpenMeteoConnector:
    return OpenMeteoConnector(BASE_URL, **kwargs)


@respx.mock
async def test_fetch_normalizes_temperature_and_humidity() -> None:
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    result = await make_connector().fetch(
        location_id="facility_001", latitude=37.77, longitude=-122.42
    )

    assert result.source is DataSource.OPEN_METEO
    assert result.data_status is DataStatus.RETRIEVED
    assert result.from_cache is False
    assert result.location_id == "facility_001"
    assert result.metrics == ("relative_humidity", "temperature")
    assert len(result.observations) == 6

    temperature = [o for o in result.observations if o.metric is Metric.TEMPERATURE]
    assert [o.value for o in temperature] == [14.2, 13.8, 13.1]
    assert all(o.unit is Unit.CELSIUS for o in temperature)
    assert temperature[0].timestamp_utc == datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
    assert temperature[0].original_timezone == "UTC"
    assert temperature[0].data_status is DataStatus.RETRIEVED


@respx.mock
async def test_requests_utc_and_the_requested_variables() -> None:
    route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    await make_connector().fetch(location_id="f", latitude=1.5, longitude=-2.5, forecast_days=3)

    request = route.calls[0].request
    assert request.url.params["timezone"] == "UTC"
    assert request.url.params["forecast_days"] == "3"
    assert request.url.params["hourly"] == "temperature_2m,relative_humidity_2m"
    assert request.url.params["latitude"] == "1.5"


@respx.mock
async def test_second_call_is_served_from_cache() -> None:
    route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    connector = make_connector()

    first = await connector.fetch(location_id="f", latitude=1.0, longitude=2.0)
    second = await connector.fetch(location_id="f", latitude=1.0, longitude=2.0)

    assert first.from_cache is False
    assert second.from_cache is True
    assert len(route.calls) == 1


@respx.mock
async def test_different_coordinates_are_cached_separately() -> None:
    route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    connector = make_connector()

    await connector.fetch(location_id="f", latitude=1.0, longitude=2.0)
    await connector.fetch(location_id="f", latitude=9.0, longitude=2.0)

    assert len(route.calls) == 2


@respx.mock
async def test_expired_cache_entry_is_refetched() -> None:
    route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    connector = make_connector(cache_ttl_seconds=-1.0)

    await connector.fetch(location_id="f", latitude=1.0, longitude=2.0)
    await connector.fetch(location_id="f", latitude=1.0, longitude=2.0)

    assert len(route.calls) == 2


@respx.mock
async def test_http_error_raises_instead_of_fabricating_data() -> None:
    respx.get(BASE_URL).mock(
        return_value=httpx.Response(400, json={"reason": "Latitude must be in range"})
    )

    with pytest.raises(UpstreamUnavailable, match="Latitude must be in range"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


@respx.mock
async def test_non_json_error_body_still_produces_a_message() -> None:
    respx.get(BASE_URL).mock(return_value=httpx.Response(503, text="<html>down</html>"))

    with pytest.raises(UpstreamUnavailable, match="HTTP 503"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


@respx.mock
async def test_timeout_raises_upstream_unavailable() -> None:
    respx.get(BASE_URL).mock(side_effect=httpx.TimeoutException("too slow"))

    with pytest.raises(UpstreamUnavailable, match="did not respond"):
        await make_connector(timeout_seconds=2.5).fetch(
            location_id="f", latitude=1.0, longitude=2.0
        )


@respx.mock
async def test_connection_error_raises_upstream_unavailable() -> None:
    respx.get(BASE_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(UpstreamUnavailable, match="Could not reach Open-Meteo"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


@respx.mock
async def test_null_values_are_not_silently_filled() -> None:
    payload = {
        "hourly": {
            "time": ["2026-09-16T00:00", "2026-09-16T01:00"],
            "temperature_2m": [14.2, None],
        }
    }
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(UpstreamUnavailable, match="null value"):
        await make_connector().fetch(
            location_id="f", latitude=1.0, longitude=2.0, variables=("temperature_2m",)
        )


@respx.mock
async def test_mismatched_series_length_is_rejected() -> None:
    payload = {
        "hourly": {"time": ["2026-09-16T00:00", "2026-09-16T01:00"], "temperature_2m": [1.0]}
    }
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(UpstreamUnavailable, match="values for temperature_2m"):
        await make_connector().fetch(
            location_id="f", latitude=1.0, longitude=2.0, variables=("temperature_2m",)
        )


@respx.mock
async def test_empty_hourly_series_is_rejected() -> None:
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={"hourly": {"time": []}}))

    with pytest.raises(UpstreamUnavailable, match="empty hourly series"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


@respx.mock
async def test_response_without_hourly_block_is_rejected() -> None:
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={"latitude": 1.0}))

    with pytest.raises(UpstreamUnavailable, match="did not contain hourly data"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


@respx.mock
async def test_non_json_response_is_rejected() -> None:
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, text="not json"))

    with pytest.raises(UpstreamUnavailable, match="non-JSON"):
        await make_connector().fetch(location_id="f", latitude=1.0, longitude=2.0)


async def test_unsupported_variable_is_rejected_before_any_request() -> None:
    with pytest.raises(ValueError, match="Unsupported Open-Meteo variable"):
        await make_connector().fetch(
            location_id="f", latitude=1.0, longitude=2.0, variables=("wind_speed_10m",)
        )


@respx.mock
async def test_unparseable_timestamp_is_rejected() -> None:
    payload = {"hourly": {"time": ["not-a-date"], "temperature_2m": [1.0]}}
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(UpstreamUnavailable, match="unparseable timestamp"):
        await make_connector().fetch(
            location_id="f", latitude=1.0, longitude=2.0, variables=("temperature_2m",)
        )


def test_attribution_is_declared() -> None:
    """Open-Meteo's licence requires attribution, so it is a constant, not a UI choice."""
    assert "Open-Meteo" in ATTRIBUTION
