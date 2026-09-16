"""Scenario endpoints: create, optimize, retrieve, export.

The optimize endpoint is synchronous. A 24-hour solve takes milliseconds, so a job queue
would add moving parts without improving the user's experience. Concurrency is bounded
instead, because SciPy releases the GIL only partially and an unbounded number of
simultaneous solves would contend for CPU on a small Railway instance.
"""

from __future__ import annotations

import csv
import io
import threading
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.dataset import Dataset
from app.models.facility import Facility
from app.models.scenario import (
    HourlyAllocation,
    OptimizationResultRecord,
    Scenario,
    ScenarioWorkload,
)
from app.optimization.problem import ObjectiveMode
from app.optimization.results import (
    HourlyPoint,
    OptimizationResult,
    SolverDiagnostics,
    SolverStatus,
)
from app.optimization.solver import solve
from app.schemas.api import ScenarioCreate, ScenarioOut
from app.services.db import get_session
from app.services.scenario_builder import build_problem

__all__ = ["router"]

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

_solver_slots = threading.BoundedSemaphore(get_settings().max_concurrent_optimizations)


def _get_scenario(session: Session, scenario_id: UUID) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No scenario with id {scenario_id}.",
        )
    return scenario


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, session: Session = Depends(get_session)) -> Scenario:
    facility = session.get(Facility, payload.facility_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No facility with id {payload.facility_id}.",
        )

    if payload.dataset_ids:
        found = set(session.scalars(select(Dataset.id).where(Dataset.id.in_(payload.dataset_ids))))
        missing = [str(item) for item in payload.dataset_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No dataset(s) with id(s) {', '.join(missing)}.",
            )

    job_ids = [workload.job_id for workload in payload.workloads]
    if len(job_ids) != len(set(job_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workload job_id values must be unique within a scenario.",
        )

    scenario = Scenario(
        facility_id=payload.facility_id,
        name=payload.name,
        objective=payload.objective.value,
        carbon_price_usd_per_tco2e=payload.carbon_price_usd_per_tco2e,
        status="draft",
        dataset_ids=[str(item) for item in payload.dataset_ids],
        workloads=[
            ScenarioWorkload(
                job_id=workload.job_id,
                energy_mwh=workload.energy_mwh,
                release_hour=workload.release_hour,
                deadline_hour=workload.deadline_hour,
                max_mw=workload.max_mw,
            )
            for workload in payload.workloads
        ],
    )
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return scenario


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(session: Session = Depends(get_session)) -> list[Scenario]:
    return list(session.scalars(select(Scenario).order_by(Scenario.created_at.desc())))


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: UUID, session: Session = Depends(get_session)) -> Scenario:
    return _get_scenario(session, scenario_id)


def _load_inputs(session: Session, scenario: Scenario) -> tuple[Facility, list[Dataset]]:
    facility = session.get(Facility, scenario.facility_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The scenario's facility no longer exists.",
        )

    if not scenario.dataset_ids:
        datasets: list[Dataset] = []
    else:
        identifiers = [UUID(item) for item in scenario.dataset_ids]
        datasets = list(session.scalars(select(Dataset).where(Dataset.id.in_(identifiers))))
    return facility, datasets


def _persist_result(
    session: Session,
    scenario: Scenario,
    result: OptimizationResult,
    timestamps: tuple[datetime, ...],
) -> OptimizationResultRecord:
    record = OptimizationResultRecord(
        scenario_id=scenario.id,
        solver_status=result.status.value,
        solver_message=result.diagnostics.message[:500],
        solver=result.diagnostics.solver,
        solve_seconds=result.diagnostics.solve_seconds,
        variables=result.diagnostics.variables,
        constraints=result.diagnostics.constraints,
        objective_value=result.objective_value,
        total_cost_usd=result.total_cost_usd,
        total_emissions_tco2e=result.total_emissions_tco2e,
        baseline_total_cost_usd=result.baseline_total_cost_usd,
        baseline_total_emissions_tco2e=result.baseline_total_emissions_tco2e,
        cost_savings_pct=result.cost_savings_pct,
        emissions_reduction_pct=result.emissions_reduction_pct,
        hourly=[point.model_dump(mode="json") for point in result.hourly],
        baseline_allocations=(
            {job_id: list(values) for job_id, values in result.baseline_allocations.items()}
            if result.baseline_allocations
            else None
        ),
        assumptions=list(result.assumptions),
        constraint_violations=list(result.constraint_violations),
    )

    for job_id, values in result.job_allocations.items():
        for hour, energy in enumerate(values):
            if energy <= 0 or hour >= len(timestamps):
                continue
            record.allocations.append(
                HourlyAllocation(
                    job_id=job_id,
                    timestamp_utc=timestamps[hour],
                    energy_mwh=energy,
                )
            )

    session.add(record)
    scenario.status = "optimized" if result.status is SolverStatus.OPTIMAL else "failed"
    session.commit()
    session.refresh(record)
    return record


@router.post("/{scenario_id}/optimize", response_model=OptimizationResult)
def optimize_scenario(
    scenario_id: UUID, session: Session = Depends(get_session)
) -> OptimizationResult:
    scenario = _get_scenario(session, scenario_id)
    settings = get_settings()

    if not _solver_slots.acquire(timeout=1.0):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"All {settings.max_concurrent_optimizations} solver slots are busy. Retry shortly."
            ),
        )
    try:
        facility, datasets = _load_inputs(session, scenario)

        # ScenarioBuildError and ProblemValidationError propagate to the application-level
        # handlers, which return one consistent shape with every reason attached.
        built = build_problem(facility, datasets, list(scenario.workloads))

        if len(scenario.workloads) > settings.max_workloads:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"The scenario has {len(scenario.workloads)} workloads; the limit is "
                    f"{settings.max_workloads}."
                ),
            )
        if built.problem.horizon_hours > settings.max_horizon_hours:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"The shared horizon is {built.problem.horizon_hours} hours; the limit "
                    f"is {settings.max_horizon_hours}."
                ),
            )

        result = solve(
            built.problem,
            ObjectiveMode(scenario.objective),
            carbon_price_usd_per_tco2e=scenario.carbon_price_usd_per_tco2e,
            time_limit_seconds=settings.solver_time_limit_seconds,
        )

        if built.assumptions:
            result = result.model_copy(
                update={"assumptions": tuple(built.assumptions) + result.assumptions}
            )

        _persist_result(session, scenario, result, built.problem.timestamps_utc)
        scenario.snapshot_checksum = built.snapshot_checksum
        session.commit()
        return result
    finally:
        _solver_slots.release()


def _latest_result(session: Session, scenario_id: UUID) -> OptimizationResultRecord:
    record = session.scalars(
        select(OptimizationResultRecord)
        .where(OptimizationResultRecord.scenario_id == scenario_id)
        .order_by(OptimizationResultRecord.created_at.desc())
        .limit(1)
    ).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This scenario has not been optimized yet. "
                f"POST /api/v1/scenarios/{scenario_id}/optimize first."
            ),
        )
    return record


def result_from_record(record: OptimizationResultRecord, scenario: Scenario) -> OptimizationResult:
    """Rebuild the domain result from storage so the API has one response shape."""
    return OptimizationResult(
        status=SolverStatus(record.solver_status),
        objective_mode=ObjectiveMode(scenario.objective),
        carbon_price_usd_per_tco2e=scenario.carbon_price_usd_per_tco2e,
        objective_value=record.objective_value,
        total_cost_usd=record.total_cost_usd,
        total_emissions_tco2e=record.total_emissions_tco2e,
        baseline_total_cost_usd=record.baseline_total_cost_usd,
        baseline_total_emissions_tco2e=record.baseline_total_emissions_tco2e,
        cost_savings_pct=record.cost_savings_pct,
        emissions_reduction_pct=record.emissions_reduction_pct,
        hourly=tuple(HourlyPoint.model_validate(point) for point in record.hourly),
        job_allocations={
            job_id: tuple(values) for job_id, values in _allocations_by_job(record).items()
        },
        baseline_allocations=(
            {job_id: tuple(values) for job_id, values in record.baseline_allocations.items()}
            if record.baseline_allocations
            else None
        ),
        diagnostics=SolverDiagnostics(
            status=SolverStatus(record.solver_status),
            message=record.solver_message,
            solver=record.solver,
            solve_seconds=record.solve_seconds,
            variables=record.variables,
            constraints=record.constraints,
            time_limit_seconds=get_settings().solver_time_limit_seconds,
        ),
        assumptions=tuple(record.assumptions),
        constraint_violations=tuple(record.constraint_violations),
    )


def _allocations_by_job(record: OptimizationResultRecord) -> dict[str, list[float]]:
    """Rebuild per-job hourly vectors from the stored allocation rows.

    The stored hourly points carry JSON timestamps while the allocation rows come back as
    datetimes, so both sides are normalized to UTC datetimes before matching.
    """
    horizon = len(record.hourly)
    vectors: dict[str, list[float]] = {}
    for allocation in record.allocations:
        vectors.setdefault(allocation.job_id, [0.0] * horizon)

    index_by_timestamp = {
        _as_utc(point["timestamp_utc"]): index for index, point in enumerate(record.hourly)
    }
    for allocation in record.allocations:
        index = index_by_timestamp.get(_as_utc(allocation.timestamp_utc))
        if index is None:
            continue
        vectors[allocation.job_id][index] = allocation.energy_mwh
    return vectors


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@router.get("/{scenario_id}/results", response_model=OptimizationResult)
def get_results(scenario_id: UUID, session: Session = Depends(get_session)) -> OptimizationResult:
    scenario = _get_scenario(session, scenario_id)
    return result_from_record(_latest_result(session, scenario.id), scenario)


@router.get("/{scenario_id}/export")
def export_results(
    scenario_id: UUID,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    session: Session = Depends(get_session),
) -> Response:
    scenario = _get_scenario(session, scenario_id)
    record = _latest_result(session, scenario.id)
    result = result_from_record(record, scenario)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = f"gridshift-{scenario.name.replace(' ', '-').lower()}-{stamp}"

    if format == "json":
        return Response(
            content=result.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "hour",
            "timestamp_utc",
            "price_usd_per_mwh",
            "carbon_tco2e_per_mwh",
            "capacity_mwh",
            "baseline_load_mwh",
            "optimized_flexible_mwh",
            "optimized_consumption_mwh",
            "baseline_flexible_mwh",
            "baseline_consumption_mwh",
            "optimized_cost_usd",
            "optimized_emissions_tco2e",
            "baseline_cost_usd",
            "baseline_emissions_tco2e",
        ]
    )
    for point in result.hourly:
        writer.writerow(
            [
                point.hour,
                point.timestamp_utc.isoformat(),
                point.price_usd_per_mwh,
                point.carbon_tco2e_per_mwh,
                point.capacity_mwh,
                point.baseline_load_mwh,
                point.optimized_flexible_mwh,
                point.optimized_consumption_mwh,
                point.baseline_flexible_mwh,
                point.baseline_consumption_mwh,
                point.optimized_cost_usd,
                point.optimized_emissions_tco2e,
                point.baseline_cost_usd,
                point.baseline_emissions_tco2e,
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
    )
