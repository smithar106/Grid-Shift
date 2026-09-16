"""Facility endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.facility import Facility
from app.models.scenario import Scenario
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


@router.delete("/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(
    facility_id: UUID,
    force: bool = Query(
        default=False,
        description="Also delete the facility's scenarios and detach its datasets.",
    ),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a facility.

    Refuses while scenarios or datasets still reference it. Cascading silently would
    destroy results the user may not have realised were attached, so the counts are
    reported and `force=true` is required to proceed. Detaching a dataset keeps its
    observations: a dataset is a record of a snapshot and may be re-used.
    """
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No facility with id {facility_id}.",
        )

    scenarios = list(session.scalars(select(Scenario).where(Scenario.facility_id == facility_id)))
    datasets = list(session.scalars(select(Dataset).where(Dataset.facility_id == facility_id)))

    if (scenarios or datasets) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Facility {facility.location_id!r} still has {len(scenarios)} scenario(s) "
                f"and {len(datasets)} dataset(s). Delete them first, or retry with "
                "?force=true to delete the scenarios and detach the datasets."
            ),
        )

    for scenario in scenarios:
        session.delete(scenario)
    for dataset in datasets:
        dataset.facility_id = None

    session.delete(facility)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
