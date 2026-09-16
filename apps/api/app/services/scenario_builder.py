"""Build a solvable problem from persisted data.

This is the join between persistence and the optimizer. It refuses ambiguous input rather
than guessing: if two datasets both supply electricity prices, the builder cannot know
which the user meant, so it says so.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.dataset import Dataset
from app.models.facility import Facility
from app.models.scenario import ScenarioWorkload
from app.optimization.problem import OptimizationProblem, Workload
from app.schemas.enums import Metric

__all__ = ["BuiltProblem", "ScenarioBuildError", "build_problem"]

HOUR = timedelta(hours=1)

#: Metrics the optimizer cannot run without.
REQUIRED_METRICS = (Metric.ELECTRICITY_PRICE, Metric.CARBON_INTENSITY)


class ScenarioBuildError(ValueError):
    """The scenario's inputs cannot be assembled into a solvable problem."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(reasons)
        super().__init__(" ".join(reasons))


@dataclass(frozen=True, slots=True)
class BuiltProblem:
    problem: OptimizationProblem
    horizon_start: datetime
    horizon_end: datetime
    datasets_used: dict[Metric, str]
    snapshot_checksum: str
    assumptions: tuple[str, ...]


def _series_by_timestamp(dataset: Dataset, metric: Metric) -> dict[datetime, float]:
    return {
        observation.timestamp_utc: observation.value
        for observation in dataset.observations
        if observation.metric == metric.value
    }


def _snapshot_checksum(datasets: list[Dataset]) -> str:
    """Fingerprint of the exact input set, so a run can be tied to its evidence."""
    digest = hashlib.sha256()
    for dataset in sorted(datasets, key=lambda item: item.checksum):
        digest.update(dataset.checksum.encode())
    return digest.hexdigest()


def build_problem(
    facility: Facility,
    datasets: list[Dataset],
    workloads: list[ScenarioWorkload],
) -> BuiltProblem:
    """Assemble an :class:`OptimizationProblem` from stored datasets and workloads.

    Raises:
        ScenarioBuildError: if required metrics are missing, ambiguous, or do not overlap.
    """
    if not datasets:
        raise ScenarioBuildError(
            [
                "The scenario has no datasets. Upload at least an electricity price series "
                "and a carbon intensity series before optimizing."
            ]
        )

    # --- Which dataset supplies which metric? ---------------------------------------
    providers: dict[Metric, list[Dataset]] = defaultdict(list)
    for dataset in datasets:
        for metric in Metric:
            if any(observation.metric == metric.value for observation in dataset.observations):
                providers[metric].append(dataset)

    reasons: list[str] = []
    for metric in REQUIRED_METRICS:
        if not providers[metric]:
            reasons.append(
                f"No dataset in this scenario provides {metric.value}. "
                "Both electricity_price and carbon_intensity are required."
            )
        elif len(providers[metric]) > 1:
            names = ", ".join(str(dataset.id) for dataset in providers[metric])
            reasons.append(
                f"{metric.value} is provided by more than one dataset ({names}). "
                "Remove one so the input is unambiguous."
            )
    if reasons:
        raise ScenarioBuildError(reasons)

    series: dict[Metric, dict[datetime, float]] = {}
    datasets_used: dict[Metric, str] = {}
    for metric, candidates in providers.items():
        dataset = candidates[0]
        series[metric] = _series_by_timestamp(dataset, metric)
        datasets_used[metric] = str(dataset.id)

    # --- Horizon: the hours every supplied series covers ----------------------------
    starts = [min(values) for values in series.values()]
    ends = [max(values) for values in series.values()]
    horizon_start = max(starts)
    horizon_end = min(ends)

    if horizon_start > horizon_end:
        raise ScenarioBuildError(
            [
                "The supplied series do not overlap in time: "
                f"the latest start is {horizon_start.isoformat()} but the earliest end is "
                f"{horizon_end.isoformat()}."
            ]
        )

    hours: list[datetime] = []
    cursor = horizon_start
    while cursor <= horizon_end:
        hours.append(cursor)
        cursor += HOUR

    # --- Align every series onto the horizon ----------------------------------------
    aligned: dict[Metric, list[float]] = {}
    for metric, values in series.items():
        column: list[float] = []
        for hour in hours:
            if hour not in values:
                raise ScenarioBuildError(
                    [
                        f"{metric.value} is missing {hour.isoformat()} inside the shared "
                        "horizon. Re-upload a complete hourly series."
                    ]
                )
            column.append(values[hour])
        aligned[metric] = column

    assumptions: list[str] = []
    baseline_load = aligned.get(Metric.FACILITY_LOAD)
    if baseline_load is None:
        baseline_load = [0.0] * len(hours)
        assumptions.append(
            "No facility_load series was supplied, so the fixed baseline load is assumed "
            "to be zero and the entire modelled consumption is flexible."
        )

    capacity = [facility.capacity_mw] * len(hours)
    assumptions.append(
        f"Electrical capacity is held at the facility rating of {facility.capacity_mw:g} MW "
        "for every hour."
    )

    # --- Workloads ------------------------------------------------------------------
    workload_objects: list[Workload] = []
    for record in workloads:
        if record.deadline_hour >= len(hours):
            raise ScenarioBuildError(
                [
                    f"Workload {record.job_id!r} has deadline_hour {record.deadline_hour} "
                    f"but the shared horizon is only {len(hours)} hours "
                    f"(0-{len(hours) - 1})."
                ]
            )
        workload_objects.append(
            Workload(
                job_id=record.job_id,
                energy_mwh=record.energy_mwh,
                release_hour=record.release_hour,
                deadline_hour=record.deadline_hour,
                max_mw=record.max_mw,
            )
        )

    problem = OptimizationProblem(
        location_id=facility.location_id,
        timestamps_utc=tuple(hours),
        price_usd_per_mwh=tuple(aligned[Metric.ELECTRICITY_PRICE]),
        carbon_tco2e_per_mwh=tuple(aligned[Metric.CARBON_INTENSITY]),
        baseline_load_mwh=tuple(baseline_load),
        capacity_mw=tuple(capacity),
        workloads=tuple(workload_objects),
    )

    return BuiltProblem(
        problem=problem,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        datasets_used=datasets_used,
        snapshot_checksum=_snapshot_checksum(datasets),
        assumptions=tuple(assumptions),
    )
