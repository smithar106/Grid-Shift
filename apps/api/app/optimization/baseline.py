"""The comparison baseline.

The optimizer is only meaningful against a baseline that is itself valid. A schedule
that quietly violates a deadline would make any "saving" fictional, so this module
produces a schedule that provably satisfies the same hard constraints, and raises rather
than returning something infeasible.

The rule is **earliest deadline first, then earliest release, then job id**. Within each
hour the job takes as much as it can, up to the headroom left by the fixed load, its own
power limit, and what it still owes. The ordering is total and the algorithm is greedy,
so the same problem always yields the same baseline.
"""

from __future__ import annotations

from app.optimization.problem import OptimizationProblem
from app.optimization.schedule import TOLERANCE, Schedule

__all__ = ["BaselineInfeasible", "earliest_feasible"]


class BaselineInfeasible(ValueError):
    """The greedy baseline could not complete every workload.

    This is reported rather than hidden: comparing the optimizer against a baseline that
    violates a deadline would overstate the benefit.
    """

    def __init__(self, unfinished: dict[str, float]) -> None:
        self.unfinished = dict(unfinished)
        detail = ", ".join(
            f"{job_id} short by {shortfall:.3f} MWh"
            for job_id, shortfall in sorted(unfinished.items())
        )
        super().__init__(
            "No earliest-feasible baseline exists: the fixed load and capacity leave "
            f"too little headroom for the requested work ({detail}). The scenario is "
            "likely infeasible."
        )


def earliest_feasible(problem: OptimizationProblem) -> Schedule:
    """Build the deterministic earliest-feasible baseline schedule.

    Raises:
        BaselineInfeasible: if the workloads cannot all be completed.
    """
    horizon = problem.horizon_hours
    interval = problem.interval_hours

    headroom = [
        capacity * interval - load
        for load, capacity in zip(problem.baseline_load_mwh, problem.capacity_mw, strict=True)
    ]

    ordered = sorted(
        problem.workloads,
        key=lambda workload: (
            workload.deadline_hour,
            workload.release_hour,
            workload.job_id,
        ),
    )

    allocations: dict[str, tuple[float, ...]] = {}
    unfinished: dict[str, float] = {}

    for workload in ordered:
        per_hour = [0.0] * horizon
        outstanding = workload.energy_mwh

        for hour in range(workload.release_hour, workload.deadline_hour + 1):
            if outstanding <= TOLERANCE:
                break
            available = min(headroom[hour], workload.max_mw * interval, outstanding)
            if available <= TOLERANCE:
                continue
            per_hour[hour] += available
            headroom[hour] -= available
            outstanding -= available

        if outstanding > TOLERANCE:
            unfinished[workload.job_id] = outstanding
        allocations[workload.job_id] = tuple(per_hour)

    if unfinished:
        raise BaselineInfeasible(unfinished)

    return Schedule(problem=problem, allocations=allocations, label="baseline")
