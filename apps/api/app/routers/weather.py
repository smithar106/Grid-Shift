"""Weather endpoint.

Weather is retrieved and displayed, but does not enter the optimization objective. The
response says so explicitly (``affects_objective: false``) so the dashboard cannot imply
otherwise.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.connectors.open_meteo import ATTRIBUTION, OpenMeteoConnector
from app.schemas.api import WeatherOut, WeatherPoint
from app.schemas.enums import Metric

__all__ = ["router"]

router = APIRouter(prefix="/weather", tags=["weather"])


def get_connector() -> OpenMeteoConnector:
    settings = get_settings()
    return OpenMeteoConnector(
        settings.open_meteo_base_url,
        timeout_seconds=settings.http_timeout_seconds,
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )


@router.get("", response_model=WeatherOut)
async def get_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    location_id: str = Query(default="facility_001", min_length=1, max_length=100),
    forecast_days: int = Query(default=2, ge=1, le=16),
    connector: OpenMeteoConnector = Depends(get_connector),
) -> WeatherOut:
    # UpstreamUnavailable propagates to the application-level handler, which returns a
    # consistent error shape. GridShift does not fabricate weather to keep a dashboard
    # populated.
    result = await connector.fetch(
        location_id=location_id,
        latitude=latitude,
        longitude=longitude,
        forecast_days=forecast_days,
    )

    by_hour: dict[datetime, WeatherPoint] = {}
    for observation in result.observations:
        point = by_hour.setdefault(
            observation.timestamp_utc, WeatherPoint(timestamp_utc=observation.timestamp_utc)
        )
        if observation.metric is Metric.TEMPERATURE:
            point.temperature_c = observation.value
        elif observation.metric is Metric.RELATIVE_HUMIDITY:
            point.relative_humidity_pct = observation.value

    return WeatherOut(
        location_id=result.location_id,
        latitude=latitude,
        longitude=longitude,
        source=result.source,
        data_status=result.data_status,
        retrieved_at=result.retrieved_at,
        from_cache=result.from_cache,
        attribution=ATTRIBUTION,
        affects_objective=False,
        points=[by_hour[key] for key in sorted(by_hour)],
    )
