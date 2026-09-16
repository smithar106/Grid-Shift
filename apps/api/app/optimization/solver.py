"""Linear-programming solver.

The model is continuous and linear, so a linear solver is the right tool: there is no
reason to pay for a mixed-integer search. SciPy's ``linprog`` with the HiGHS backend is
used for v1. A mixed-integer solver becomes necessary only when binary activation,
minimum run times, or non-preemptible jobs are modelled.

Formulation
-----------
Decision variables ``x[j,t]`` exist only for hours inside job ``j``'s window, which
enforces the "no processing outside the window" constraint structurally rather than with
extra rows.

    minimize    sum_t w[t] * (b[t] + sum_j x[j,t])
    subject to  sum_t x[j,t] = W[j]                     for every job j
                b[t] + sum_j x[j,t] <= K[t] * dt        for every hour t
                0 <= x[j,t] <= M[j] * dt                for every variable

where ``w[t]`` is the price (cost mode), the carbon intensity (emissions mode), or
``p[t] + lambda * c[t]`` (balanced mode).

Because ``sum_t w[t] * b[t]`` is constant, the objective value reported by the solver
differs from the true objective by that constant; the constant is added back so the
reported value is the real cost or emissions of the schedule.
"""

from __future__ import annotations

import time

import numpy as np
from scipy import sparse
from scipy.optimize import linprog

from app.optimization.baseline import BaselineInfeasible, earliest_feasible
from app.optimization.problem import (
    ObjectiveMode,
    OptimizationProblem,
)
from app.optimization.results import (
    HourlyPoint,
    OptimizationResult,
    SolverDiagnostics,
    SolverStatus,
)
from app.optimization.schedule import TOLERANCE, Schedule

__all__ = ["ASSUMPTIONS", "solve"]

#: Status codes returned by scipy.optimize.linprog.
_STATUS_MAP = {
    0: SolverStatus.OPTIMAL,
    1: SolverStatus.TIME_LIMIT,
    2: SolverStatus.INFEASIBLE,
    3: SolverStatus.UNBOUNDED,
    4: SolverStatus.NUMERICAL_ERROR,
}

ASSUMPTIONS = (
    "Workloads are divisible and preemptible; no minimum run time or activation cost is modelled.",
    "Baseline facility load is fixed and cannot be shifted.",
    "Electrical capacity limits energy per hour to capacity_mw x interval_hours.",
    "Electricity prices and carbon intensity are treated as supplied inputs, not as "
    "forward-looking forecasts.",
    "The baseline is the deterministic earliest-feasible schedule (earliest deadline "
    "first, then earliest release, then job id).",
)


def _pct_change(baseline: float, optimized: float) -> float | None:
    """Percentage reduction from baseline to optimized, or None if undefined.

    Negative values are preserved: improving one objective can worsen the other, and
    hiding that would misrepresent the trade-off.
    """
    if abs(baseline) < TOLERANCE:
        return None
    return (baseline - optimized) / baseline * 100.0


def _infeasible_result(
    problem: OptimizationProblem,
    mode: ObjectiveMode,
    carbon_price: float,
    reasons: list[str],
    started: float,
    variables: int,
    constraints: int,
    time_limit: float,
) -> OptimizationResult:
    return OptimizationResult(
        status=SolverStatus.INFEASIBLE,
        objective_mode=mode,
        carbon_price_usd_per_tco2e=carbon_price,
        objective_value=0.0,
        total_cost_usd=0.0,
        total_emissions_tco2e=0.0,
        diagnostics=SolverDiagnostics(
            status=SolverStatus.INFEASIBLE,
            message=" ".join(reasons),
            solve_seconds=time.perf_counter() - started,
            variables=variables,
            constraints=constraints,
            time_limit_seconds=time_limit,
        ),
        assumptions=ASSUMPTIONS,
    )


def _build_hourly(
    problem: OptimizationProblem,
    optimized: Schedule,
    baseline: Schedule | None,
) -> tuple[HourlyPoint, ...]:
    interval = problem.interval_hours
    optimized_flexible = optimized.flexible_mwh
    optimized_total = optimized.consumption_mwh
    baseline_flexible = baseline.flexible_mwh if baseline else (0.0,) * problem.horizon_hours
    baseline_total = baseline.consumption_mwh if baseline else problem.baseline_load_mwh

    points = []
    for hour in range(problem.horizon_hours):
        price = problem.price_usd_per_mwh[hour]
        carbon = problem.carbon_tco2e_per_mwh[hour]
        points.append(
            HourlyPoint(
                hour=hour,
                timestamp_utc=problem.timestamps_utc[hour],
                price_usd_per_mwh=price,
                carbon_tco2e_per_mwh=carbon,
                capacity_mwh=problem.capacity_mw[hour] * interval,
                baseline_load_mwh=problem.baseline_load_mwh[hour],
                optimized_flexible_mwh=optimized_flexible[hour],
                optimized_consumption_mwh=optimized_total[hour],
                baseline_flexible_mwh=baseline_flexible[hour],
                baseline_consumption_mwh=baseline_total[hour],
                optimized_cost_usd=price * optimized_total[hour],
                optimized_emissions_tco2e=carbon * optimized_total[hour],
                baseline_cost_usd=price * baseline_total[hour],
                baseline_emissions_tco2e=carbon * baseline_total[hour],
            )
        )
    return tuple(points)


def solve(
    problem: OptimizationProblem,
    mode: ObjectiveMode = ObjectiveMode.COST,
    *,
    carbon_price_usd_per_tco2e: float = 0.0,
    time_limit_seconds: float = 5.0,
) -> OptimizationResult:
    """Minimize the chosen objective subject to every hard constraint.

    Args:
        problem: A validated, self-contained scheduling problem.
        mode: Which objective to minimize.
        carbon_price_usd_per_tco2e: ``lambda``, only used by balanced mode.
        time_limit_seconds: Solver time limit; a timeout is reported, not hidden.
    """
    started = time.perf_counter()

    if carbon_price_usd_per_tco2e < 0:
        raise ValueError("carbon_price_usd_per_tco2e must be non-negative.")

    weights = problem.objective_coefficients(mode, carbon_price_usd_per_tco2e)
    baseline_constant = sum(
        weight * load for weight, load in zip(weights, problem.baseline_load_mwh, strict=True)
    )

    # --- Pre-checks: report the specific reason instead of a generic infeasibility ---
    reasons: list[str] = []
    for workload in problem.workloads:
        if workload.energy_mwh > workload.window_capacity_mwh + TOLERANCE:
            reasons.append(
                f"Workload {workload.job_id!r} requires {workload.energy_mwh:.3f} MWh but "
                f"can absorb at most {workload.window_capacity_mwh:.3f} MWh in its "
                f"{workload.window_hours}-hour window at {workload.max_mw:.3f} MW."
            )
    if reasons:
        return _infeasible_result(
            problem, mode, carbon_price_usd_per_tco2e, reasons, started, 0, 0, time_limit_seconds
        )

    # --- Baseline -------------------------------------------------------------------
    baseline: Schedule | None = None
    baseline_note: str | None = None
    try:
        baseline = earliest_feasible(problem)
    except BaselineInfeasible as exc:
        baseline_note = str(exc)

    # --- Variables ------------------------------------------------------------------
    columns: list[tuple[int, int]] = []
    for job_index, workload in enumerate(problem.workloads):
        for hour in range(workload.release_hour, workload.deadline_hour + 1):
            columns.append((job_index, hour))

    variable_count = len(columns)
    constraint_count = len(problem.workloads) + problem.horizon_hours
    interval = problem.interval_hours

    if variable_count == 0:
        # No flexible work: the schedule is exactly the fixed load. Reported as optimal
        # rather than as an error, because it is a valid answer.
        schedule = Schedule(problem=problem, allocations={}, label="optimized")
        return _finalize(
            problem=problem,
            mode=mode,
            carbon_price=carbon_price_usd_per_tco2e,
            schedule=schedule,
            baseline=baseline,
            status=SolverStatus.OPTIMAL,
            message="No flexible workloads were supplied; the schedule is the fixed load.",
            iterations=None,
            started=started,
            variables=0,
            constraints=constraint_count,
            time_limit=time_limit_seconds,
            extra_notes=[baseline_note] if baseline_note else [],
        )

    coefficient_vector = np.array([weights[hour] for _, hour in columns], dtype=float)

    eq_rows: list[int] = []
    eq_cols: list[int] = []
    for column, (job_index, _) in enumerate(columns):
        eq_rows.append(job_index)
        eq_cols.append(column)
    a_eq = sparse.csr_matrix(
        (np.ones(variable_count), (eq_rows, eq_cols)),
        shape=(len(problem.workloads), variable_count),
    )
    b_eq = np.array([workload.energy_mwh for workload in problem.workloads], dtype=float)

    ub_rows: list[int] = []
    ub_cols: list[int] = []
    for column, (_, hour) in enumerate(columns):
        ub_rows.append(hour)
        ub_cols.append(column)
    a_ub = sparse.csr_matrix(
        (np.ones(variable_count), (ub_rows, ub_cols)),
        shape=(problem.horizon_hours, variable_count),
    )
    b_ub = np.array(
        [
            problem.capacity_mw[hour] * interval - problem.baseline_load_mwh[hour]
            for hour in range(problem.horizon_hours)
        ],
        dtype=float,
    )

    bounds = [(0.0, problem.workloads[job_index].max_mw * interval) for job_index, _ in columns]

    solution = linprog(
        c=coefficient_vector,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
        options={"time_limit": time_limit_seconds, "presolve": True},
    )

    status = _STATUS_MAP.get(solution.status, SolverStatus.NUMERICAL_ERROR)

    if status is not SolverStatus.OPTIMAL or solution.x is None:
        message = solution.message or "The solver did not return a solution."
        return OptimizationResult(
            status=status,
            objective_mode=mode,
            carbon_price_usd_per_tco2e=carbon_price_usd_per_tco2e,
            objective_value=0.0,
            total_cost_usd=0.0,
            total_emissions_tco2e=0.0,
            baseline_total_cost_usd=baseline.cost_usd if baseline else None,
            baseline_total_emissions_tco2e=baseline.emissions_tco2e if baseline else None,
            baseline_allocations=dict(baseline.allocations) if baseline else None,
            diagnostics=SolverDiagnostics(
                status=status,
                message=message,
                solve_seconds=time.perf_counter() - started,
                variables=variable_count,
                constraints=constraint_count,
                time_limit_seconds=time_limit_seconds,
                iterations=getattr(solution, "nit", None),
            ),
            assumptions=ASSUMPTIONS,
        )

    allocations: dict[str, list[float]] = {
        workload.job_id: [0.0] * problem.horizon_hours for workload in problem.workloads
    }
    for column, (job_index, hour) in enumerate(columns):
        allocations[problem.workloads[job_index].job_id][hour] = float(solution.x[column])

    schedule = Schedule(
        problem=problem,
        allocations={job_id: tuple(values) for job_id, values in allocations.items()},
        label="optimized",
    )

    return _finalize(
        problem=problem,
        mode=mode,
        carbon_price=carbon_price_usd_per_tco2e,
        schedule=schedule,
        baseline=baseline,
        status=SolverStatus.OPTIMAL,
        message=solution.message or "Optimal solution found.",
        iterations=getattr(solution, "nit", None),
        started=started,
        variables=variable_count,
        constraints=constraint_count,
        time_limit=time_limit_seconds,
        extra_notes=[baseline_note] if baseline_note else [],
        objective_value=float(solution.fun) + baseline_constant,
    )


def _finalize(
    *,
    problem: OptimizationProblem,
    mode: ObjectiveMode,
    carbon_price: float,
    schedule: Schedule,
    baseline: Schedule | None,
    status: SolverStatus,
    message: str,
    iterations: int | None,
    started: float,
    variables: int,
    constraints: int,
    time_limit: float,
    extra_notes: list[str],
    objective_value: float | None = None,
) -> OptimizationResult:
    """Assemble the result, verifying the solver's answer before returning it."""
    violations = schedule.constraint_violations()

    cost = schedule.cost_usd
    emissions = schedule.emissions_tco2e

    if objective_value is None:
        objective_value = sum(
            weight * consumption
            for weight, consumption in zip(
                problem.objective_coefficients(mode, carbon_price),
                schedule.consumption_mwh,
                strict=True,
            )
        )

    assumptions = list(ASSUMPTIONS)
    if mode is ObjectiveMode.BALANCED:
        assumptions.append(
            f"Balanced mode charges carbon at {carbon_price:g} USD per tonne CO2e; the "
            "cost and emissions shown are the modelled quantities, not the combined "
            "objective."
        )
    if mode is ObjectiveMode.COST:
        assumptions.append(
            "Cost mode ignores emissions; emissions are reported for comparison only."
        )
    if mode is ObjectiveMode.EMISSIONS:
        assumptions.append("Emissions mode ignores price; cost is reported for comparison only.")
    if violations:
        assumptions.append(
            "The solver returned a solution that violates a hard constraint; it is "
            "reported as a numerical error rather than as a usable schedule."
        )
    assumptions.extend(extra_notes)

    if violations and status is SolverStatus.OPTIMAL:
        status = SolverStatus.NUMERICAL_ERROR
        message = "Solver output failed post-solve constraint verification: " + "; ".join(
            violations[:3]
        )

    baseline_cost = baseline.cost_usd if baseline else None
    baseline_emissions = baseline.emissions_tco2e if baseline else None

    return OptimizationResult(
        status=status,
        objective_mode=mode,
        carbon_price_usd_per_tco2e=carbon_price,
        objective_value=objective_value,
        total_cost_usd=cost,
        total_emissions_tco2e=emissions,
        baseline_total_cost_usd=baseline_cost,
        baseline_total_emissions_tco2e=baseline_emissions,
        cost_savings_pct=(_pct_change(baseline_cost, cost) if baseline_cost is not None else None),
        emissions_reduction_pct=(
            _pct_change(baseline_emissions, emissions) if baseline_emissions is not None else None
        ),
        hourly=_build_hourly(problem, schedule, baseline),
        job_allocations={job_id: tuple(values) for job_id, values in schedule.allocations.items()},
        baseline_allocations=(
            {job_id: tuple(values) for job_id, values in baseline.allocations.items()}
            if baseline
            else None
        ),
        diagnostics=SolverDiagnostics(
            status=status,
            message=message,
            solve_seconds=time.perf_counter() - started,
            variables=variables,
            constraints=constraints,
            time_limit_seconds=time_limit,
            iterations=iterations,
        ),
        assumptions=tuple(assumptions),
        constraint_violations=tuple(violations),
    )
