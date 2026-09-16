"""Problem-shape validation and objective construction."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.optimization.problem import (
    ObjectiveMode,
    OptimizationProblem,
    ProblemValidationError,
    Workload,
)

HOURS = 4


def test_rejects_series_shorter_than_horizon() -> None:
    with pytest.raises(ProblemValidationError, match="price_usd_per_mwh has 2 values"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * 4,
            price_usd_per_mwh=(1.0, 2.0),
            carbon_tco2e_per_mwh=(0.5,) * 4,
            baseline_load_mwh=(1.0,) * 4,
            capacity_mw=(10.0,) * 4,
        )


def test_rejects_negative_capacity() -> None:
    with pytest.raises(ProblemValidationError, match="capacity_mw\\[1\\] is negative"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * 2,
            price_usd_per_mwh=(1.0, 1.0),
            carbon_tco2e_per_mwh=(0.5, 0.5),
            baseline_load_mwh=(1.0, 1.0),
            capacity_mw=(10.0, -1.0),
        )


def test_rejects_negative_carbon_intensity() -> None:
    with pytest.raises(ProblemValidationError, match="carbon_tco2e_per_mwh\\[0\\]"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),),
            price_usd_per_mwh=(1.0,),
            carbon_tco2e_per_mwh=(-0.1,),
            baseline_load_mwh=(1.0,),
            capacity_mw=(10.0,),
        )


def test_rejects_negative_baseline_load() -> None:
    with pytest.raises(ProblemValidationError, match="baseline_load_mwh\\[0\\]"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),),
            price_usd_per_mwh=(1.0,),
            carbon_tco2e_per_mwh=(0.5,),
            baseline_load_mwh=(-1.0,),
            capacity_mw=(10.0,),
        )


def test_baseline_load_above_capacity_is_a_problem_error() -> None:
    """Flexible work cannot repair an overload: the fixed load cannot move."""
    with pytest.raises(ProblemValidationError, match="exceeds electrical capacity"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * 2,
            price_usd_per_mwh=(1.0, 1.0),
            carbon_tco2e_per_mwh=(0.5, 0.5),
            baseline_load_mwh=(1.0, 99.0),
            capacity_mw=(10.0, 10.0),
        )


def test_rejects_duplicate_job_ids() -> None:
    with pytest.raises(ProblemValidationError, match="Duplicate job_id"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * HOURS,
            price_usd_per_mwh=(1.0,) * HOURS,
            carbon_tco2e_per_mwh=(0.5,) * HOURS,
            baseline_load_mwh=(1.0,) * HOURS,
            capacity_mw=(10.0,) * HOURS,
            workloads=(
                Workload(job_id="a", energy_mwh=1, release_hour=0, deadline_hour=1, max_mw=1),
                Workload(job_id="a", energy_mwh=1, release_hour=0, deadline_hour=1, max_mw=1),
            ),
        )


def test_rejects_deadline_beyond_horizon() -> None:
    with pytest.raises(ProblemValidationError, match="beyond the horizon"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * HOURS,
            price_usd_per_mwh=(1.0,) * HOURS,
            carbon_tco2e_per_mwh=(0.5,) * HOURS,
            baseline_load_mwh=(1.0,) * HOURS,
            capacity_mw=(10.0,) * HOURS,
            workloads=(
                Workload(job_id="a", energy_mwh=1, release_hour=0, deadline_hour=99, max_mw=1),
            ),
        )


def test_rejects_deadline_before_release() -> None:
    with pytest.raises(ProblemValidationError, match="before"):
        Workload(job_id="a", energy_mwh=1, release_hour=5, deadline_hour=2, max_mw=1)


@pytest.mark.parametrize(
    ("field", "value"),
    [("energy_mwh", 0.0), ("energy_mwh", -1.0), ("max_mw", 0.0), ("max_mw", -2.0)],
)
def test_rejects_non_positive_workload_magnitudes(field: str, value: float) -> None:
    payload = {
        "job_id": "a",
        "energy_mwh": 1.0,
        "release_hour": 0,
        "deadline_hour": 1,
        "max_mw": 1.0,
    }
    payload[field] = value
    with pytest.raises(ProblemValidationError, match="positive finite number"):
        Workload(**payload)  # type: ignore[arg-type]


def test_rejects_blank_job_id() -> None:
    with pytest.raises(ProblemValidationError, match="non-empty string"):
        Workload(job_id="   ", energy_mwh=1, release_hour=0, deadline_hour=1, max_mw=1)


def test_rejects_negative_release_hour() -> None:
    with pytest.raises(ProblemValidationError, match="release_hour cannot be negative"):
        Workload(job_id="a", energy_mwh=1, release_hour=-1, deadline_hour=1, max_mw=1)


def test_rejects_blank_location_id() -> None:
    with pytest.raises(ProblemValidationError, match="location_id must be a non-empty"):
        OptimizationProblem(
            location_id="  ",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),),
            price_usd_per_mwh=(1.0,),
            carbon_tco2e_per_mwh=(0.5,),
            baseline_load_mwh=(1.0,),
            capacity_mw=(10.0,),
        )


def test_rejects_empty_horizon() -> None:
    with pytest.raises(ProblemValidationError, match="at least one hour"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(),
            price_usd_per_mwh=(),
            carbon_tco2e_per_mwh=(),
            baseline_load_mwh=(),
            capacity_mw=(),
        )


@pytest.mark.parametrize("interval", [0.0, -1.0, float("inf")])
def test_rejects_invalid_interval_hours(interval: float) -> None:
    with pytest.raises(ProblemValidationError, match="interval_hours"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),),
            price_usd_per_mwh=(1.0,),
            carbon_tco2e_per_mwh=(0.5,),
            baseline_load_mwh=(1.0,),
            capacity_mw=(10.0,),
            interval_hours=interval,
        )


def test_rejects_non_finite_series_values() -> None:
    with pytest.raises(ProblemValidationError, match="not a finite number"):
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * 2,
            price_usd_per_mwh=(1.0, float("nan")),
            carbon_tco2e_per_mwh=(0.5, 0.5),
            baseline_load_mwh=(1.0, 1.0),
            capacity_mw=(10.0, 10.0),
        )


def test_reports_a_truncated_list_when_many_hours_are_overloaded() -> None:
    """The message must not dump dozens of hour indices."""
    with pytest.raises(ProblemValidationError) as error:
        OptimizationProblem(
            location_id="f",
            timestamps_utc=(datetime(2026, 9, 16, tzinfo=UTC),) * 8,
            price_usd_per_mwh=(1.0,) * 8,
            carbon_tco2e_per_mwh=(0.5,) * 8,
            baseline_load_mwh=(99.0,) * 8,
            capacity_mw=(10.0,) * 8,
        )
    assert "and 3 more" in str(error.value)


def test_workload_window_helpers() -> None:
    workload = Workload(job_id="a", energy_mwh=10, release_hour=2, deadline_hour=5, max_mw=3)
    assert workload.window_hours == 4
    assert workload.window_capacity_mwh == 12


def test_objective_coefficients_cost_mode(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=3, prices=[1.0, 2.0, 3.0])
    assert problem.objective_coefficients(ObjectiveMode.COST, 100.0) == (1.0, 2.0, 3.0)


def test_objective_coefficients_emissions_mode_ignores_carbon_price(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=2, carbons=[0.1, 0.9])
    assert problem.objective_coefficients(ObjectiveMode.EMISSIONS, 999.0) == (0.1, 0.9)


def test_objective_coefficients_balanced_mode_combines_units(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Balanced mode must not add dollars to tonnes; it prices carbon first."""
    problem = build_problem(hours=2, prices=[10.0, 20.0], carbons=[0.5, 0.1])
    assert problem.objective_coefficients(ObjectiveMode.BALANCED, 100.0) == (60.0, 30.0)


def test_horizon_and_total_energy_helpers(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=6,
        workloads=[("a", 10.0, 0, 5, 5.0), ("b", 2.5, 1, 2, 5.0)],
    )
    assert problem.horizon_hours == 6
    assert problem.total_flexible_energy_mwh == pytest.approx(12.5)
