"""Optimization result contracts.

Every response carries the solver's own status, the modeled cost *and* emissions
regardless of which objective was minimized, and the assumptions the numbers rest on.
A combined objective never hides the two quantities it trades off.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.optimization.problem import ObjectiveMode

__all__ = ["HourlyPoint", "OptimizationResult", "SolverDiagnostics", "SolverStatus"]


class SolverStatus(StrEnum):
    OPTIMAL = "optimal"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    TIME_LIMIT = "time_limit"
    NUMERICAL_ERROR = "numerical_error"


class SolverDiagnostics(BaseModel):
    """Everything needed to reproduce and audit a solve."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SolverStatus
    message: str
    solver: str = "scipy.optimize.linprog (HiGHS)"
    solve_seconds: float = Field(ge=0)
    variables: int = Field(ge=0)
    constraints: int = Field(ge=0)
    time_limit_seconds: float = Field(gt=0)
    iterations: int | None = None


class HourlyPoint(BaseModel):
    """One hour of the horizon, with both schedules side by side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hour: int = Field(ge=0)
    timestamp_utc: datetime

    price_usd_per_mwh: float
    carbon_tco2e_per_mwh: float
    capacity_mwh: float

    baseline_load_mwh: float
    optimized_flexible_mwh: float
    optimized_consumption_mwh: float
    baseline_flexible_mwh: float
    baseline_consumption_mwh: float

    optimized_cost_usd: float
    optimized_emissions_tco2e: float
    baseline_cost_usd: float
    baseline_emissions_tco2e: float


class OptimizationResult(BaseModel):
    """The outcome of one solve, including the comparison against the baseline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SolverStatus
    objective_mode: ObjectiveMode
    carbon_price_usd_per_tco2e: float = Field(ge=0)

    objective_value: float
    total_cost_usd: float
    total_emissions_tco2e: float

    baseline_total_cost_usd: float | None = None
    baseline_total_emissions_tco2e: float | None = None
    cost_savings_pct: float | None = None
    emissions_reduction_pct: float | None = None

    hourly: tuple[HourlyPoint, ...] = ()
    job_allocations: dict[str, tuple[float, ...]] = Field(default_factory=dict)
    baseline_allocations: dict[str, tuple[float, ...]] | None = None

    diagnostics: SolverDiagnostics
    assumptions: tuple[str, ...] = ()
    constraint_violations: tuple[str, ...] = ()
