"""Facility endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facility import Facility
from app.schemas.api import FacilityCreate, FacilityOut
from app.services.db import get_session

__all__ = ["router"]

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.post("", response_model=FacilityOut, status_code=status.HTTP_201_CREATED)
def create_facility(payload: FacilityCreate, session: Session = Depends(get_session)) -> Facility:
    existing = session.scalar(select(Facility).where(Facility.location_id == payload.location_id))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A facility with location_id {payload.location_id!r} already exists "
                f"(id {existing.id}). Use a different location_id."
            ),
        )

    facility = Facility(**payload.model_dump())
    session.add(facility)
    session.commit()
    session.refresh(facility)
    return facility


@router.get("", response_model=list[FacilityOut])
def list_facilities(session: Session = Depends(get_session)) -> list[Facility]:
    return list(session.scalars(select(Facility).order_by(Facility.created_at.desc())))


@router.get("/{facility_id}", response_model=FacilityOut)
def get_facility(facility_id: UUID, session: Session = Depends(get_session)) -> Facility:
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No facility with id {facility_id}.",
        )
    return facility
