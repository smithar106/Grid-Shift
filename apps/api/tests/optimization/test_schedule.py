"""The schedule arithmetic is shared by the optimizer and the baseline, so it is tested
directly: a bug here would corrupt both sides of the comparison."""

from __future__ import annotations

import pytest

from app.optimization.schedule import Schedule


def test_aggregates_flexible_and_total_consumption(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=3,
        loads=[5.0, 6.0, 7.0],
        capacities=[20.0] * 3,
        workloads=[("a", 3.0, 0, 2, 5.0), ("b", 3.0, 0, 2, 5.0)],
    )
    schedule = Schedule(
        problem=problem,
        allocations={"a": (1.0, 2.0, 0.0), "b": (0.0, 1.0, 2.0)},
    )

    assert schedule.flexible_mwh == (1.0, 3.0, 2.0)
    assert schedule.consumption_mwh == (6.0, 9.0, 9.0)
    assert schedule.job_totals == {"a": 3.0, "b": 3.0}


def test_cost_and_emissions_use_price_and_carbon_series(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=2,
        prices=[10.0, 20.0],
        carbons=[0.5, 0.25],
        loads=[0.0, 0.0],
        capacities=[100.0] * 2,
        workloads=[("a", 4.0, 0, 1, 100.0)],
    )
    schedule = Schedule(problem=problem, allocations={"a": (2.0, 2.0)})

    assert schedule.cost_usd == pytest.approx(2.0 * 10.0 + 2.0 * 20.0)
    assert schedule.emissions_tco2e == pytest.approx(2.0 * 0.5 + 2.0 * 0.25)


def test_valid_schedule_reports_no_violations(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=4,
        loads=[1.0] * 4,
        capacities=[10.0] * 4,
        workloads=[("a", 6.0, 1, 3, 2.0)],
    )
    schedule = Schedule(problem=problem, allocations={"a": (0.0, 2.0, 2.0, 2.0)})

    assert schedule.constraint_violations() == []
    schedule.assert_valid()


def test_detects_incomplete_workload(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=2, workloads=[("a", 10.0, 0, 1, 10.0)])
    schedule = Schedule(problem=problem, allocations={"a": (3.0, 3.0)})

    assert any("requires" in violation for violation in schedule.constraint_violations())


def test_detects_capacity_overrun(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=1, loads=[8.0], capacities=[10.0], workloads=[("a", 5.0, 0, 0, 100.0)]
    )
    schedule = Schedule(problem=problem, allocations={"a": (5.0,)})

    assert any("above the" in violation for violation in schedule.constraint_violations())


def test_detects_job_power_limit_breach(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=1, workloads=[("a", 5.0, 0, 0, 1.0)])
    schedule = Schedule(problem=problem, allocations={"a": (5.0,)})

    assert any("above its" in violation for violation in schedule.constraint_violations())


def test_detects_work_outside_the_window(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=3, workloads=[("a", 1.0, 2, 2, 5.0)])
    schedule = Schedule(problem=problem, allocations={"a": (1.0, 0.0, 0.0)})

    assert any("outside its window" in violation for violation in schedule.constraint_violations())


def test_detects_negative_allocation(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=2, workloads=[("a", 1.0, 0, 1, 5.0)])
    schedule = Schedule(problem=problem, allocations={"a": (2.0, -1.0)})

    assert any("negative energy" in violation for violation in schedule.constraint_violations())


def test_detects_unknown_job(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=1)
    schedule = Schedule(problem=problem, allocations={"ghost": (1.0,)})

    assert any("unknown job" in violation for violation in schedule.constraint_violations())


def test_detects_wrong_hourly_length(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=3, workloads=[("a", 1.0, 0, 2, 5.0)])
    schedule = Schedule(problem=problem, allocations={"a": (1.0,)})

    assert any("hourly values" in violation for violation in schedule.constraint_violations())


def test_assert_valid_raises_with_a_readable_message(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=2, workloads=[("a", 10.0, 0, 1, 10.0)])
    schedule = Schedule(problem=problem, allocations={"a": (1.0, 1.0)}, label="optimized")

    with pytest.raises(AssertionError, match="optimized violates constraints"):
        schedule.assert_valid()
