"""Normalized observation contracts.

These models are the single interchange format between connectors, the ingestion
service, persistence, and the optimizer. A connector that cannot satisfy them must
fail loudly rather than degrade the data.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums import DataSource, DataStatus, Metric, Unit

__all__ = ["Observation", "ObservationSeries"]


class Observation(BaseModel):
    """One measured value for one metric, at one hour, in canonical units.

    ``value`` and ``unit`` are canonical: downstream math never has to know that the
    user uploaded kilowatt-hours or kilograms of CO2e. The values exactly as supplied
    are retained in the ``original_*`` fields for provenance.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp_utc: datetime
    location_id: str = Field(min_length=1)
    metric: Metric
    value: float
    unit: Unit
    source: DataSource
    data_status: DataStatus

    original_timestamp: str
    original_timezone: str
    original_value: float
    original_unit: Unit
    retrieved_at: datetime

    @field_validator("timestamp_utc", "retrieved_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware.")
        return value.astimezone(UTC)

    @field_validator("value", "original_value")
    @classmethod
    def _require_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Value must be a finite number.")
        return value


class ObservationSeries(BaseModel):
    """A single metric for a single location, ordered and gap-checked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location_id: str = Field(min_length=1)
    metric: Metric
    unit: Unit
    observations: tuple[Observation, ...]

    #: True when every hour between start and end is present exactly once.
    is_contiguous: bool
    #: Set when the caller explicitly accepted gaps.
    gaps: tuple[datetime, ...] = ()

    @model_validator(mode="after")
    def _validate_series(self) -> Self:
        if not self.observations:
            raise ValueError(f"Series for {self.metric} is empty.")

        for observation in self.observations:
            if observation.metric is not self.metric:
                raise ValueError(
                    f"Series for {self.metric} contains a {observation.metric} observation."
                )
            if observation.location_id != self.location_id:
                raise ValueError(
                    f"Series for {self.location_id} contains a "
                    f"{observation.location_id} observation."
                )
            if observation.unit is not self.unit:
                raise ValueError(
                    f"Series unit {self.unit} conflicts with observation unit {observation.unit}."
                )

        expected = tuple(sorted(o.timestamp_utc for o in self.observations))
        actual = tuple(o.timestamp_utc for o in self.observations)
        if actual != expected:
            raise ValueError(f"Series for {self.metric} is not sorted by timestamp_utc.")

        return self

    @property
    def start_utc(self) -> datetime:
        return self.observations[0].timestamp_utc

    @property
    def end_utc(self) -> datetime:
        return self.observations[-1].timestamp_utc

    @property
    def hours(self) -> int:
        return len(self.observations)

    @property
    def total(self) -> float:
        return sum(observation.value for observation in self.observations)

    @property
    def peak(self) -> float:
        return max(observation.value for observation in self.observations)

    def dense_values(self) -> list[float]:
        """Return one value per hour, requiring a gap-free series.

        The optimizer's capacity and deadline constraints are defined per contiguous
        hour, so a gap would silently shift every later hour.
        """
        if not self.is_contiguous:
            raise ValueError(
                f"Series for {self.metric} has {len(self.gaps)} missing hour(s) and "
                "cannot be densified."
            )
        return [observation.value for observation in self.observations]
