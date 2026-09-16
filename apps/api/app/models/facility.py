"""Facilities.

A facility is the physical site whose fixed load and electrical capacity bound the
optimization. Its ``location_id`` is the identifier that observations carry, which is what
lets a dataset be joined to the facility it describes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UtcDateTime, utcnow

__all__ = ["Facility"]


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    location_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")

    capacity_mw: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<Facility {self.location_id} capacity={self.capacity_mw}MW>"
