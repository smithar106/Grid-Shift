"""Open-Meteo connector.

Open-Meteo provides hourly weather forecasts without an API key, which makes it the one
external source the MVP can depend on. Attribution is required; the free hosted tier is
for non-commercial use.

Scope note: weather is displayed alongside the optimization but does **not** influence the
objective unless a weather-to-cooling-load model is explicitly enabled. Presenting weather
as if it drove the schedule would overstate what the model does.

API documentation: https://open-meteo.com/en/docs
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.base import ConnectorResult, UpstreamUnavailable
from app.connectors.cache import ResponseCache, cache_key
from app.schemas.enums import DataSource, DataStatus, Metric, Unit
from app.schemas.observations import Observation

__all__ = ["OpenMeteoConnector"]

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

#: Open-Meteo variable name -> GridShift metric and unit.
VARIABLES: dict[str, tuple[Metric, Unit]] = {
    "temperature_2m": (Metric.TEMPERATURE, Unit.CELSIUS),
    "relative_humidity_2m": (Metric.RELATIVE_HUMIDITY, Unit.PERCENT),
}


class OpenMeteoConnector:
    """Retrieves hourly weather and normalizes it into GridShift observations."""

    source = DataSource.OPEN_METEO

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: float = 900.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._cache = ResponseCache(ttl_seconds=cache_ttl_seconds)
        self._client = client

    async def _get(self, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        key = cache_key(self._base_url, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached, True

        payload = await self._request(params)
        self._cache.set(key, payload)
        return payload, False

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.get(self._base_url, params=params)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamUnavailable(
                f"Open-Meteo did not respond within {self._timeout:g}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Could not reach Open-Meteo: {exc}") from exc

        if response.status_code >= 400:
            raise UpstreamUnavailable(
                f"Open-Meteo returned HTTP {response.status_code}: {self._error_detail(response)}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamUnavailable("Open-Meteo returned a non-JSON response.") from exc

        if not isinstance(payload, dict) or "hourly" not in payload:
            raise UpstreamUnavailable("Open-Meteo response did not contain hourly data.")
        return payload

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:200] or "no detail"
        if isinstance(body, dict) and "reason" in body:
            return str(body["reason"])
        return str(body)[:200]

    async def fetch(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_days: int = 2,
        variables: tuple[str, ...] = ("temperature_2m", "relative_humidity_2m"),
        retrieved_at: datetime | None = None,
    ) -> ConnectorResult:
        """Fetch hourly weather for a location.

        Raises:
            UpstreamUnavailable: if Open-Meteo cannot be read. No synthetic fallback is
                produced.
        """
        unknown = [name for name in variables if name not in VARIABLES]
        if unknown:
            supported = ", ".join(sorted(VARIABLES))
            raise ValueError(
                f"Unsupported Open-Meteo variable(s): {', '.join(unknown)}. Supported: {supported}."
            )

        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(variables),
            "timezone": "UTC",
            "forecast_days": forecast_days,
        }

        payload, from_cache = await self._get(params)
        moment = retrieved_at or datetime.now(UTC)

        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise UpstreamUnavailable("Open-Meteo returned an empty hourly series.")

        observations: list[Observation] = []
        for variable in variables:
            metric, unit = VARIABLES[variable]
            values = hourly.get(variable) or []
            if len(values) != len(times):
                raise UpstreamUnavailable(
                    f"Open-Meteo returned {len(values)} values for {variable} but "
                    f"{len(times)} timestamps."
                )
            for raw_time, raw_value in zip(times, values, strict=True):
                if raw_value is None:
                    raise UpstreamUnavailable(
                        f"Open-Meteo returned a null value for {variable} at {raw_time}. "
                        "GridShift will not fill gaps with synthetic data."
                    )
                timestamp_utc = self._parse_time(raw_time)
                observations.append(
                    Observation(
                        timestamp_utc=timestamp_utc,
                        location_id=location_id,
                        metric=metric,
                        value=float(raw_value),
                        unit=unit,
                        source=DataSource.OPEN_METEO,
                        data_status=DataStatus.RETRIEVED,
                        original_timestamp=str(raw_time),
                        original_timezone="UTC",
                        original_value=float(raw_value),
                        original_unit=unit,
                        retrieved_at=moment,
                    )
                )

        return ConnectorResult(
            source=DataSource.OPEN_METEO,
            data_status=DataStatus.RETRIEVED,
            retrieved_at=moment,
            location_id=location_id,
            observations=tuple(observations),
            from_cache=from_cache,
        )

    @staticmethod
    def _parse_time(raw: str) -> datetime:
        """Open-Meteo returns 'YYYY-MM-DDTHH:MM' with no offset; we request UTC."""
        try:
            return datetime.fromisoformat(raw).replace(tzinfo=UTC)
        except ValueError as exc:
            raise UpstreamUnavailable(
                f"Open-Meteo returned an unparseable timestamp: {raw!r}."
            ) from exc
