"""HTTP request and response contracts.

Response models reuse the domain contracts (`OptimizationResult`, `IngestionReport`)
rather than restating them, so the API can never drift from what the solver actually
produced.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.optimization.problem import ObjectiveMode
from app.schemas.enums import DataSource, DataStatus
from app.schemas.ingestion import SeriesSummary

__all__ = [
    "DatasetOut",
    "FacilityCreate",
    "FacilityOut",
    "HealthOut",
    "ScenarioCreate",
    "ScenarioOut",
    "WeatherOut",
    "WeatherPoint",
    "WorkloadInput",
    "WorkloadOut",
]


class HealthOut(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class FacilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    location_id: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    capacity_mw: float = Field(gt=0, description="Available electrical capacity.")


class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location_id: str
    latitude: float | None
    longitude: float | None
    timezone: str
    capacity_mw: float
    created_at: datetime


class WorkloadInput(BaseModel):
    """A job to schedule. Hour indices are relative to the scenario horizon."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=100)
    energy_mwh: float = Field(gt=0)
    release_hour: int = Field(ge=0)
    deadline_hour: int = Field(ge=0)
    max_mw: float = Field(gt=0)


class WorkloadOut(WorkloadInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: UUID
    name: str = Field(min_length=1, max_length=200)
    objective: ObjectiveMode = ObjectiveMode.COST
    carbon_price_usd_per_tco2e: float = Field(default=0.0, ge=0)
    dataset_ids: list[UUID] = Field(default_factory=list)
    workloads: list[WorkloadInput] = Field(default_factory=list)


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    name: str
    objective: str
    carbon_price_usd_per_tco2e: float
    status: str
    dataset_ids: list[str]
    snapshot_checksum: str | None
    created_at: datetime
    workloads: list[WorkloadOut]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID | None
    source: str
    data_status: str
    metrics: list[str]
    retrieved_at: datetime
    created_at: datetime
    checksum: str
    rows_read: int
    rows_accepted: int
    original_filename: str | None
    series: list[SeriesSummary] = Field(default_factory=list)

    @field_validator("metrics", mode="before")
    @classmethod
    def _split_metrics(cls, value: object) -> object:
        """The column stores a comma-joined string; the API returns a list."""
        if isinstance(value, str):
            return [item for item in (part.strip() for part in value.split(",")) if item]
        return value


class WeatherPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_utc: datetime
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None


class WeatherOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    latitude: float
    longitude: float
    source: DataSource
    data_status: DataStatus
    retrieved_at: datetime
    from_cache: bool
    attribution: str
    #: Weather is context for the operator; it does not enter the objective unless a
    #: cooling-load model is explicitly enabled.
    affects_objective: bool = False
    points: list[WeatherPoint]
