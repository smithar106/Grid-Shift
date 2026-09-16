"""Datasets and their observations.

A dataset is one uploaded or retrieved snapshot. Its ``checksum`` is the content hash
computed at ingestion, which is what makes a run reproducible: the same snapshot always
hashes the same way, and the stored observations are the exact inputs the solver consumed.

Nothing here is ever overwritten in place. A re-upload creates a new dataset, so an old
scenario can always be re-derived from the snapshot it names.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import UtcDateTime, utcnow

__all__ = ["Dataset", "HourlyObservation"]


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Optional link: a dataset can exist before it is attached to a facility.
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source: Mapped[str] = mapped_column(String(50))
    data_status: Mapped[str] = mapped_column(String(50))
    metrics: Mapped[str] = mapped_column(String(200))

    retrieved_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    checksum: Mapped[str] = mapped_column(String(64), index=True)
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    observations: Mapped[list[HourlyObservation]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Dataset {self.id} metrics={self.metrics} checksum={self.checksum[:8]}>"


class HourlyObservation(Base):
    """One canonical observation, with the values exactly as they were supplied."""

    __tablename__ = "hourly_observations"
    __table_args__ = (
        Index("ix_hourly_observations_lookup", "dataset_id", "metric", "timestamp_utc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )

    timestamp_utc: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    location_id: Mapped[str] = mapped_column(String(100))
    metric: Mapped[str] = mapped_column(String(50))
    value: Mapped[float]
    unit: Mapped[str] = mapped_column(String(30))

    source: Mapped[str] = mapped_column(String(50))
    data_status: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(UtcDateTime)

    # Provenance: what the user actually wrote, before canonicalization.
    original_timestamp: Mapped[str] = mapped_column(String(64))
    original_timezone: Mapped[str] = mapped_column(String(100))
    original_value: Mapped[float]
    original_unit: Mapped[str] = mapped_column(String(30))

    dataset: Mapped[Dataset] = relationship(back_populates="observations")

    def __repr__(self) -> str:
        return f"<Observation {self.metric}@{self.timestamp_utc.isoformat()} {self.value}>"
