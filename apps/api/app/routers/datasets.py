"""Dataset upload, listing, and retrieval.

Uploads are validated before anything is written. A rejected file leaves no partial rows
behind, so the database never holds a dataset the user believes was accepted.
"""

from __future__ import annotations

from itertools import pairwise
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, HourlyObservation
from app.models.facility import Facility
from app.schemas.api import DatasetOut
from app.schemas.enums import Metric, Unit
from app.schemas.ingestion import SeriesSummary
from app.services.csv_ingest import IngestedDataset, ingest_csv_bytes
from app.services.db import get_session

__all__ = ["router", "summarize_dataset"]

router = APIRouter(prefix="/datasets", tags=["datasets"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def summarize_dataset(dataset: Dataset) -> list[SeriesSummary]:
    """Recompute per-metric summaries from the stored observations.

    Derived on read rather than stored, so the summary can never disagree with the rows it
    describes.
    """
    grouped: dict[str, list[HourlyObservation]] = {}
    for observation in dataset.observations:
        grouped.setdefault(observation.metric, []).append(observation)

    summaries: list[SeriesSummary] = []
    for metric, observations in grouped.items():
        ordered = sorted(observations, key=lambda item: item.timestamp_utc)
        timestamps = [item.timestamp_utc for item in ordered]
        gaps = [
            (current - previous).total_seconds() != 3600.0
            for previous, current in pairwise(timestamps)
        ]
        values = [item.value for item in ordered]
        summaries.append(
            SeriesSummary(
                metric=Metric(metric),
                unit=Unit(ordered[0].unit),
                hours=len(ordered),
                start_utc=timestamps[0],
                end_utc=timestamps[-1],
                minimum=min(values),
                maximum=max(values),
                total=sum(values),
                is_contiguous=not any(gaps),
            )
        )
    return sorted(summaries, key=lambda item: item.metric.value)


def _persist(session: Session, ingested: IngestedDataset, **dataset_fields: object) -> Dataset:
    dataset = Dataset(
        source=ingested.source.value,
        data_status=ingested.data_status.value,
        metrics=",".join(sorted(metric.value for metric in ingested.series)),
        retrieved_at=ingested.retrieved_at,
        checksum=ingested.checksum,
        rows_read=ingested.report.rows_read,
        rows_accepted=ingested.report.rows_accepted,
        **dataset_fields,
    )
    for series in ingested.series.values():
        for observation in series.observations:
            dataset.observations.append(
                HourlyObservation(
                    timestamp_utc=observation.timestamp_utc,
                    location_id=observation.location_id,
                    metric=observation.metric.value,
                    value=observation.value,
                    unit=observation.unit.value,
                    source=observation.source.value,
                    data_status=observation.data_status.value,
                    retrieved_at=observation.retrieved_at,
                    original_timestamp=observation.original_timestamp,
                    original_timezone=observation.original_timezone,
                    original_value=observation.original_value,
                    original_unit=observation.original_unit.value,
                )
            )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(..., description="Hourly CSV with timestamp, metric, value, unit"),
    facility_id: UUID | None = Form(default=None),
    timezone: str | None = Form(default=None),
    allow_gaps: bool = Form(default=False),
    session: Session = Depends(get_session),
) -> DatasetOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"The file is {len(raw)} bytes; the limit is {MAX_UPLOAD_BYTES} bytes. "
                "Upload a smaller snapshot."
            ),
        )

    default_location_id = "facility_001"
    if facility_id is not None:
        facility = session.get(Facility, facility_id)
        if facility is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No facility with id {facility_id}.",
            )
        default_location_id = facility.location_id

    try:
        ingested = ingest_csv_bytes(
            raw,
            default_location_id=default_location_id,
            default_timezone=timezone,
            allow_gaps=allow_gaps,
        )
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The file is not valid UTF-8 text.",
        ) from exc
    # DatasetValidationError is deliberately not caught here: the application-level
    # handler turns it into a single consistent error shape with every issue attached.

    dataset = _persist(
        session,
        ingested,
        facility_id=facility_id,
        original_filename=file.filename,
    )

    payload = DatasetOut.model_validate(dataset)
    payload.series = summarize_dataset(dataset)
    return payload


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    facility_id: UUID | None = None, session: Session = Depends(get_session)
) -> list[DatasetOut]:
    statement = select(Dataset).order_by(Dataset.created_at.desc())
    if facility_id is not None:
        statement = statement.where(Dataset.facility_id == facility_id)

    results = []
    for dataset in session.scalars(statement):
        payload = DatasetOut.model_validate(dataset)
        payload.series = summarize_dataset(dataset)
        results.append(payload)
    return results


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: UUID, session: Session = Depends(get_session)) -> DatasetOut:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dataset with id {dataset_id}.",
        )
    payload = DatasetOut.model_validate(dataset)
    payload.series = summarize_dataset(dataset)
    return payload
