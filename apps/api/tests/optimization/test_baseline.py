"""The earliest-feasible baseline must be valid, deterministic, and honest about failure."""

from __future__ import annotations

import pytest

from app.optimization.baseline import BaselineInfeasible, earliest_feasible


def test_baseline_completes_every_workload(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=24,
        workloads=[("batch", 120.0, 0, 23, 20.0)],
    )
    schedule = earliest_feasible(problem)

    assert schedule.constraint_violations() == []
    assert schedule.job_totals["batch"] == pytest.approx(120.0)


def test_baseline_schedules_as_early_as_possible(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Earliest-feasible means the work lands at the front of the window."""
    problem = build_problem(
        hours=8,
        capacities=[40.0] * 8,
        loads=[0.0] * 8,
        workloads=[("batch", 60.0, 0, 7, 20.0)],
    )
    schedule = earliest_feasible(problem)

    assert schedule.allocations["batch"] == (20.0, 20.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_baseline_respects_the_release_hour(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=8,
        capacities=[40.0] * 8,
        loads=[0.0] * 8,
        workloads=[("late", 40.0, 4, 7, 20.0)],
    )
    schedule = earliest_feasible(problem)

    assert schedule.allocations["late"] == (0.0, 0.0, 0.0, 0.0, 20.0, 20.0, 0.0, 0.0)


def test_baseline_respects_the_job_power_limit(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=6,
        capacities=[50.0] * 6,
        loads=[0.0] * 6,
        workloads=[("small", 30.0, 0, 5, 5.0)],
    )
    schedule = earliest_feasible(problem)

    assert all(value <= 5.0 + 1e-9 for value in schedule.allocations["small"])
    assert schedule.allocations["small"] == (5.0, 5.0, 5.0, 5.0, 5.0, 5.0)


def test_baseline_leaves_headroom_for_the_fixed_load(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=4,
        capacities=[30.0] * 4,
        loads=[25.0] * 4,
        workloads=[("batch", 20.0, 0, 3, 20.0)],
    )
    schedule = earliest_feasible(problem)

    # Only 5 MWh of headroom per hour, so 20 MWh takes all four hours.
    assert schedule.allocations["batch"] == (5.0, 5.0, 5.0, 5.0)
    assert schedule.constraint_violations() == []


def test_baseline_never_exceeds_capacity(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=12,
        capacities=[15.0] * 12,
        loads=[12.0] * 12,
        workloads=[("a", 18.0, 0, 11, 10.0), ("b", 9.0, 3, 8, 10.0)],
    )
    schedule = earliest_feasible(problem)

    assert schedule.constraint_violations() == []
    for hour, consumption in enumerate(schedule.consumption_mwh):
        assert consumption <= 15.0 + 1e-9, f"hour {hour} over capacity"


def test_baseline_orders_by_earliest_deadline(build_problem) -> None:  # type: ignore[no-untyped-def]
    """The urgent job must win the scarce early capacity."""
    problem = build_problem(
        hours=2,
        capacities=[10.0] * 2,
        loads=[0.0] * 2,
        workloads=[
            ("relaxed", 10.0, 0, 1, 10.0),
            ("urgent", 10.0, 0, 0, 10.0),
        ],
    )
    schedule = earliest_feasible(problem)

    assert schedule.allocations["urgent"] == (10.0, 0.0)
    assert schedule.allocations["relaxed"] == (0.0, 10.0)
    assert schedule.constraint_violations() == []


def test_baseline_is_deterministic(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=10,
        capacities=[20.0] * 10,
        loads=[5.0] * 10,
        workloads=[("a", 30.0, 0, 9, 8.0), ("b", 15.0, 2, 7, 8.0)],
    )
    first = earliest_feasible(problem)
    second = earliest_feasible(problem)

    assert first.allocations == second.allocations
    assert first.cost_usd == second.cost_usd


def test_baseline_raises_when_work_cannot_fit(build_problem) -> None:  # type: ignore[no-untyped-def]
    """A baseline that silently violated a deadline would inflate any saving."""
    problem = build_problem(
        hours=2,
        capacities=[10.0] * 2,
        loads=[0.0] * 2,
        workloads=[("impossible", 100.0, 0, 1, 10.0)],
    )
    with pytest.raises(BaselineInfeasible, match="earliest-feasible baseline"):
        earliest_feasible(problem)


def test_baseline_reports_which_jobs_were_short(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=1,
        capacities=[10.0] * 1,
        loads=[0.0] * 1,
        workloads=[("short", 25.0, 0, 0, 10.0)],
    )
    with pytest.raises(BaselineInfeasible) as error:
        earliest_feasible(problem)

    assert "short" in error.value.unfinished
    assert error.value.unfinished["short"] == pytest.approx(15.0)


def test_baseline_handles_no_workloads(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=3)
    schedule = earliest_feasible(problem)

    assert schedule.allocations == {}
    assert schedule.consumption_mwh == (10.0, 10.0, 10.0)
