"""The optimization problem definition.

This module is deliberately free of solver code. It describes *what* GridShift optimizes,
so the model can be unit-tested, serialized into a snapshot, and reasoned about without
running a solver.

These are plain frozen dataclasses rather than pydantic models. The API layer owns
request/response contracts; this is an internal domain object, and using pydantic here
would wrap every semantic error in a generic ``ValidationError`` and bury the specific
reason a problem is unusable.

Notation (matching docs/OPTIMIZATION.md):

    T           number of hourly intervals in the horizon
    b[t]        fixed facility load in hour t           (MWh)
    K[t]        available electrical capacity in hour t  (MW)
    p[t]        electricity price in hour t              (USD/MWh)
    c[t]        emissions intensity in hour t            (tCO2e/MWh)
    W[j]        energy a job must complete               (MWh)
    r[j], d[j]  release and deadline hour indices (inclusive)
    M[j]        maximum processing power for a job       (MW)
    x[j,t]      energy committed to job j in hour t      (MWh, decision variable)

Total consumption is E[t] = b[t] + sum_j x[j,t].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

__all__ = [
    "ObjectiveMode",
    "OptimizationProblem",
    "ProblemValidationError",
    "Workload",
]


class ObjectiveMode(StrEnum):
    """Which linear objective the solver minimizes."""

    COST = "cost"
    EMISSIONS = "emissions"
    BALANCED = "balanced"


class ProblemValidationError(ValueError):
    """Raised when a problem is internally inconsistent and cannot be solved.

    Distinct from *infeasibility*: an infeasible problem is well-formed but has no
    solution, whereas an invalid problem is malformed and would produce a meaningless
    answer.
    """

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(reasons)
        super().__init__("; ".join(reasons))


@dataclass(frozen=True, slots=True)
class Workload:
    """A divisible, preemptible job that must complete within its window.

    The MVP does not model non-preemptible jobs, minimum run times, or activation costs.
    Those require a mixed-integer formulation and are explicitly out of scope.
    """

    job_id: str
    energy_mwh: float
    release_hour: int
    deadline_hour: int
    max_mw: float

    def __post_init__(self) -> None:
        reasons: list[str] = []
        if not self.job_id or not self.job_id.strip():
            reasons.append("Workload job_id must be a non-empty string.")
        if not math.isfinite(self.energy_mwh) or self.energy_mwh <= 0:
            reasons.append(
                f"Workload {self.job_id!r} energy_mwh must be a positive finite number, "
                f"got {self.energy_mwh}."
            )
        if not math.isfinite(self.max_mw) or self.max_mw <= 0:
            reasons.append(
                f"Workload {self.job_id!r} max_mw must be a positive finite number, "
                f"got {self.max_mw}."
            )
        if self.release_hour < 0:
            reasons.append(
                f"Workload {self.job_id!r} release_hour cannot be negative ({self.release_hour})."
            )
        if self.deadline_hour < self.release_hour:
            reasons.append(
                f"Workload {self.job_id!r} has deadline_hour {self.deadline_hour} before "
                f"release_hour {self.release_hour}."
            )
        if reasons:
            raise ProblemValidationError(reasons)

    @property
    def window_hours(self) -> int:
        """Number of hours the job is allowed to run in, inclusive of both endpoints."""
        return self.deadline_hour - self.release_hour + 1

    @property
    def window_capacity_mwh(self) -> float:
        """Most energy the job could absorb if it ran at max power for its whole window."""
        return self.max_mw * self.window_hours


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    """A complete, self-contained statement of the scheduling problem."""

    location_id: str
    timestamps_utc: tuple[datetime, ...]
    price_usd_per_mwh: tuple[float, ...]
    carbon_tco2e_per_mwh: tuple[float, ...]
    baseline_load_mwh: tuple[float, ...]
    capacity_mw: tuple[float, ...]
    workloads: tuple[Workload, ...] = ()
    interval_hours: float = field(default=1.0)

    def __post_init__(self) -> None:
        reasons: list[str] = []
        horizon = len(self.timestamps_utc)

        if not self.location_id or not self.location_id.strip():
            reasons.append("location_id must be a non-empty string.")
        if horizon == 0:
            reasons.append("The horizon must contain at least one hour.")
        if not math.isfinite(self.interval_hours) or self.interval_hours <= 0:
            reasons.append(
                f"interval_hours must be a positive finite number, got {self.interval_hours}."
            )

        for name, series in (
            ("price_usd_per_mwh", self.price_usd_per_mwh),
            ("carbon_tco2e_per_mwh", self.carbon_tco2e_per_mwh),
            ("baseline_load_mwh", self.baseline_load_mwh),
            ("capacity_mw", self.capacity_mw),
        ):
            if len(series) != horizon:
                reasons.append(
                    f"{name} has {len(series)} values but the horizon has {horizon} hours."
                )
            for index, value in enumerate(series):
                if not math.isfinite(value):
                    reasons.append(f"{name}[{index}] is not a finite number ({value}).")

        for index, capacity in enumerate(self.capacity_mw):
            if capacity < 0:
                reasons.append(f"capacity_mw[{index}] is negative ({capacity}).")

        for index, carbon in enumerate(self.carbon_tco2e_per_mwh):
            if carbon < 0:
                reasons.append(f"carbon_tco2e_per_mwh[{index}] is negative ({carbon}).")

        for index, load in enumerate(self.baseline_load_mwh):
            if load < 0:
                reasons.append(f"baseline_load_mwh[{index}] is negative ({load}).")

        if reasons:
            raise ProblemValidationError(reasons)

        # Baseline load above capacity is a data error, not an optimization outcome: no
        # schedule of flexible work can repair it, because the fixed load cannot move.
        overloaded = [
            index
            for index, (load, capacity) in enumerate(
                zip(self.baseline_load_mwh, self.capacity_mw, strict=True)
            )
            if load > capacity + 1e-9
        ]
        if overloaded:
            hours = ", ".join(str(index) for index in overloaded[:5])
            if len(overloaded) > 5:
                hours += f", and {len(overloaded) - 5} more"
            raise ProblemValidationError(
                [
                    "Fixed baseline load exceeds electrical capacity in hour(s) "
                    f"{hours}. Reduce the baseline load or raise capacity; flexible "
                    "workloads cannot resolve this because the fixed load cannot move."
                ]
            )

        seen: set[str] = set()
        for workload in self.workloads:
            if workload.job_id in seen:
                reasons.append(f"Duplicate job_id {workload.job_id!r}.")
            seen.add(workload.job_id)
            if workload.deadline_hour >= horizon:
                reasons.append(
                    f"Workload {workload.job_id!r} has deadline_hour "
                    f"{workload.deadline_hour} beyond the horizon (0-{horizon - 1})."
                )
        if reasons:
            raise ProblemValidationError(reasons)

    @property
    def horizon_hours(self) -> int:
        return len(self.timestamps_utc)

    @property
    def total_flexible_energy_mwh(self) -> float:
        return sum(workload.energy_mwh for workload in self.workloads)

    def objective_coefficients(
        self, mode: ObjectiveMode, carbon_price_usd_per_tco2e: float
    ) -> tuple[float, ...]:
        """Per-hour objective weight applied to consumption.

        Balanced mode prices carbon before combining, so dollars are never added to
        tonnes. The baseline load contributes a constant to the objective, so only the
        flexible allocations influence the argmin; both parts use this same vector, which
        keeps the reported objective consistent with the reported cost and emissions.
        """
        if mode is ObjectiveMode.COST:
            return self.price_usd_per_mwh
        if mode is ObjectiveMode.EMISSIONS:
            return self.carbon_tco2e_per_mwh
        return tuple(
            price + carbon_price_usd_per_tco2e * carbon
            for price, carbon in zip(self.price_usd_per_mwh, self.carbon_tco2e_per_mwh, strict=True)
        )
