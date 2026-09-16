"""The essential optimization tests from the PRD, plus the boundary cases around them.

Every assertion here is about the mathematics, not the plumbing: feasibility, optimality
relative to a valid baseline, and the arithmetic of the reported cost and emissions.
"""

from __future__ import annotations

import pytest

from app.optimization.problem import ObjectiveMode
from app.optimization.solver import ASSUMPTIONS, solve

# --- 1. Constant prices: the objective value is knowable by hand --------------------

HOURS = 24
JOB = ("batch", 120.0, 0, 23, 20.0)


def test_constant_prices_produce_expected_objective_value(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Fixed load 10 MWh/h plus 120 MWh of work = 360 MWh at 50 USD/MWh."""
    problem = build_problem(
        hours=HOURS, prices=[50.0] * HOURS, carbons=[0.5] * HOURS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal"
    assert result.total_cost_usd == pytest.approx(360.0 * 50.0)
    assert result.objective_value == pytest.approx(360.0 * 50.0)
    assert result.total_emissions_tco2e == pytest.approx(360.0 * 0.5)


def test_constant_emissions_objective_matches_hand_calculation(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=HOURS, carbons=[0.25] * HOURS, workloads=[JOB])
    result = solve(problem, ObjectiveMode.EMISSIONS)

    assert result.total_emissions_tco2e == pytest.approx(360.0 * 0.25)
    assert result.objective_value == pytest.approx(360.0 * 0.25)


def test_balanced_objective_adds_priced_carbon_to_cost(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Objective = cost + lambda * emissions, with lambda in USD per tonne."""
    problem = build_problem(
        hours=HOURS, prices=[50.0] * HOURS, carbons=[0.5] * HOURS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=40.0)

    assert result.objective_value == pytest.approx(360.0 * 50.0 + 40.0 * 360.0 * 0.5)
    # The dashboard must still be able to show the two quantities separately.
    assert result.total_cost_usd == pytest.approx(18000.0)
    assert result.total_emissions_tco2e == pytest.approx(180.0)


# --- 2. Cheap hours receive the flexible demand -------------------------------------

CHEAP_LATE_PRICES = [90.0] * 16 + [20.0] * 8
CHEAP_LATE_CARBONS = [0.6] * 16 + [0.2] * 8


def test_lower_price_hours_receive_flexible_demand(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.COST)

    flexible = [point.optimized_flexible_mwh for point in result.hourly]
    assert sum(flexible[:16]) == pytest.approx(0.0, abs=1e-6)
    assert sum(flexible[16:]) == pytest.approx(120.0)


def test_cost_optimization_beats_the_baseline(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.baseline_total_cost_usd is not None
    assert result.total_cost_usd < result.baseline_total_cost_usd
    assert result.cost_savings_pct is not None
    assert result.cost_savings_pct == pytest.approx(31.343, abs=0.01)


def test_carbon_intensity_drives_the_emissions_solution(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.EMISSIONS)

    flexible = [point.optimized_flexible_mwh for point in result.hourly]
    assert sum(flexible[:16]) == pytest.approx(0.0, abs=1e-6)
    assert sum(flexible[16:]) == pytest.approx(120.0)


# --- 3. Infeasibility is reported, never guessed ------------------------------------


def test_impossible_deadline_returns_infeasible_status(build_problem) -> None:  # type: ignore[no-untyped-def]
    """100 MWh cannot fit in a single hour capped at 20 MW."""
    problem = build_problem(hours=HOURS, workloads=[("too-big", 100.0, 5, 5, 20.0)])
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "infeasible"
    assert "too-big" in result.diagnostics.message
    assert result.hourly == ()
    assert result.constraint_violations == ()


def test_competing_deadlines_can_be_infeasible(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Both jobs individually fit their windows, but not together in shared capacity."""
    problem = build_problem(
        hours=2,
        loads=[0.0] * 2,
        capacities=[10.0] * 2,
        workloads=[("flexible", 15.0, 0, 1, 10.0), ("pinned", 10.0, 1, 1, 10.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "infeasible"
    assert result.diagnostics.message


def test_total_energy_beyond_capacity_is_infeasible(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=2,
        loads=[0.0] * 2,
        capacities=[10.0] * 2,
        workloads=[("a", 20.0, 0, 1, 10.0), ("b", 20.0, 0, 1, 10.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "infeasible"


def test_infeasible_scenario_reports_no_baseline_and_says_why(build_problem) -> None:  # type: ignore[no-untyped-def]
    """If no valid baseline exists, the result must say so rather than compare anyway."""
    problem = build_problem(
        hours=2,
        loads=[0.0] * 2,
        capacities=[10.0] * 2,
        workloads=[("flexible", 15.0, 0, 1, 10.0), ("pinned", 10.0, 1, 1, 10.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "infeasible"
    assert result.baseline_total_cost_usd is None
    assert result.cost_savings_pct is None
    assert any("baseline" in assumption.lower() for assumption in result.assumptions)


# --- 4. Fixed load never moves ------------------------------------------------------


def test_fixed_baseline_consumption_never_moves(build_problem) -> None:  # type: ignore[no-untyped-def]
    loads = [float(10 + (hour % 5)) for hour in range(HOURS)]
    problem = build_problem(hours=HOURS, prices=CHEAP_LATE_PRICES, loads=loads, workloads=[JOB])
    result = solve(problem, ObjectiveMode.COST)

    for point in result.hourly:
        assert point.baseline_load_mwh == pytest.approx(loads[point.hour])
        assert point.optimized_consumption_mwh - point.optimized_flexible_mwh == pytest.approx(
            loads[point.hour]
        )


# --- 5 and 6. Hard constraints hold -------------------------------------------------


def test_all_workloads_complete_within_their_deadlines(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS,
        prices=CHEAP_LATE_PRICES,
        workloads=[
            ("a", 40.0, 0, 5, 10.0),
            ("b", 25.0, 6, 12, 8.0),
            ("c", 15.0, 18, 23, 5.0),
        ],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal"
    assert result.constraint_violations == ()
    assert result.job_allocations["a"] and sum(result.job_allocations["a"]) == pytest.approx(40.0)
    assert sum(result.job_allocations["b"]) == pytest.approx(25.0)
    assert sum(result.job_allocations["c"]) == pytest.approx(15.0)

    for job_id, (_, _, release, deadline, _) in {
        "a": ("a", 40.0, 0, 5, 10.0),
        "b": ("b", 25.0, 6, 12, 8.0),
        "c": ("c", 15.0, 18, 23, 5.0),
    }.items():
        per_hour = result.job_allocations[job_id]
        for hour, energy in enumerate(per_hour):
            if not (release <= hour <= deadline):
                assert energy == pytest.approx(0.0, abs=1e-9)


def test_total_hourly_consumption_never_exceeds_capacity(build_problem) -> None:  # type: ignore[no-untyped-def]
    capacities = [float(20 + (hour % 7)) for hour in range(HOURS)]
    problem = build_problem(
        hours=HOURS,
        capacities=capacities,
        loads=[12.0] * HOURS,
        prices=CHEAP_LATE_PRICES,
        workloads=[("a", 60.0, 0, 23, 10.0), ("b", 30.0, 4, 20, 6.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.constraint_violations == ()
    for point in result.hourly:
        assert point.optimized_consumption_mwh <= capacities[point.hour] + 1e-6


def test_job_power_limit_is_respected(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS,
        capacities=[100.0] * HOURS,
        loads=[0.0] * HOURS,
        workloads=[("slow", 48.0, 0, 23, 2.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert all(value <= 2.0 + 1e-9 for value in result.job_allocations["slow"])
    assert sum(result.job_allocations["slow"]) == pytest.approx(48.0)


# --- 7 and 8. Optimization never loses to a valid baseline ---------------------------


SCENARIOS = [
    ("spiky", [10.0, 200.0] * 12, [0.1, 0.9] * 12, [5.0] * 24, [30.0] * 24),
    ("flat", [50.0] * 24, [0.5] * 24, [10.0] * 24, [40.0] * 24),
    ("cheap-early", [5.0] * 12 + [80.0] * 12, [0.9] * 12 + [0.1] * 12, [8.0] * 24, [35.0] * 24),
    ("tight", [40.0, 120.0] * 12, [0.7, 0.2] * 12, [18.0] * 24, [26.0] * 24),
]


@pytest.mark.parametrize(("name", "prices", "carbons", "loads", "capacities"), SCENARIOS)
def test_cost_optimization_never_costs_more_than_a_feasible_baseline(
    build_problem,
    name: str,
    prices,
    carbons,
    loads,
    capacities,  # type: ignore[no-untyped-def]
) -> None:
    problem = build_problem(
        hours=HOURS,
        prices=prices,
        carbons=carbons,
        loads=loads,
        capacities=capacities,
        workloads=[("batch", 60.0, 0, 23, 12.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal", name
    assert result.baseline_total_cost_usd is not None
    # Tolerance covers floating-point noise only; the optimum must not be worse.
    assert result.total_cost_usd <= result.baseline_total_cost_usd + 1e-6, name


@pytest.mark.parametrize(("name", "prices", "carbons", "loads", "capacities"), SCENARIOS)
def test_emissions_optimization_never_emits_more_than_a_feasible_baseline(
    build_problem,
    name: str,
    prices,
    carbons,
    loads,
    capacities,  # type: ignore[no-untyped-def]
) -> None:
    problem = build_problem(
        hours=HOURS,
        prices=prices,
        carbons=carbons,
        loads=loads,
        capacities=capacities,
        workloads=[("batch", 60.0, 0, 23, 12.0)],
    )
    result = solve(problem, ObjectiveMode.EMISSIONS)

    assert result.status.value == "optimal", name
    assert result.baseline_total_emissions_tco2e is not None
    assert result.total_emissions_tco2e <= result.baseline_total_emissions_tco2e + 1e-9, name


# --- 9. Zero flexible demand --------------------------------------------------------


def test_zero_flexible_demand_returns_a_valid_unchanged_schedule(build_problem) -> None:  # type: ignore[no-untyped-def]
    loads = [12.0] * HOURS
    problem = build_problem(hours=HOURS, loads=loads, workloads=[])
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal"
    assert result.constraint_violations == ()
    assert result.job_allocations == {}
    assert [point.optimized_consumption_mwh for point in result.hourly] == pytest.approx(loads)
    assert result.total_cost_usd == pytest.approx(result.baseline_total_cost_usd or 0.0)
    assert result.cost_savings_pct == pytest.approx(0.0)


# --- 11 and 12. Price edge cases ----------------------------------------------------


def test_negative_prices_are_exploited_within_constraints(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Negative prices mean being paid to consume; the optimum must seek them out."""
    prices = [50.0] * 20 + [-50.0] * 4
    problem = build_problem(
        hours=HOURS,
        prices=prices,
        carbons=[0.5] * HOURS,
        workloads=[("batch", 40.0, 0, 23, 20.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal"
    assert result.constraint_violations == ()
    flexible = [point.optimized_flexible_mwh for point in result.hourly]
    assert sum(flexible[20:]) == pytest.approx(40.0)
    assert sum(flexible[:20]) == pytest.approx(0.0, abs=1e-6)
    assert result.baseline_total_cost_usd is not None
    assert result.total_cost_usd < result.baseline_total_cost_usd


def test_zero_price_intervals_are_used_first(build_problem) -> None:  # type: ignore[no-untyped-def]
    prices = [0.0] * 6 + [100.0] * 18
    problem = build_problem(
        hours=HOURS,
        prices=prices,
        carbons=[0.5] * HOURS,
        workloads=[("batch", 120.0, 0, 23, 20.0)],
    )
    result = solve(problem, ObjectiveMode.COST)

    flexible = [point.optimized_flexible_mwh for point in result.hourly]
    assert sum(flexible[:6]) == pytest.approx(120.0)
    assert sum(flexible[6:]) == pytest.approx(0.0, abs=1e-6)


# --- Balanced mode ------------------------------------------------------------------

DIRTY_CHEAP = [10.0] * 12 + [30.0] * 12
DIRTY_CHEAP_CARBONS = [1.0] * 12 + [0.1] * 12


def test_balanced_mode_shifts_load_as_the_carbon_price_rises(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS,
        prices=DIRTY_CHEAP,
        carbons=DIRTY_CHEAP_CARBONS,
        workloads=[("batch", 120.0, 0, 23, 20.0)],
    )
    without_carbon_price = solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=0.0)
    with_carbon_price = solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=100.0)

    cheap_dirty = sum(point.optimized_flexible_mwh for point in without_carbon_price.hourly[:12])
    clean_expensive = sum(point.optimized_flexible_mwh for point in with_carbon_price.hourly[:12])

    assert cheap_dirty == pytest.approx(120.0)
    assert clean_expensive == pytest.approx(0.0, abs=1e-6)
    assert with_carbon_price.total_emissions_tco2e < without_carbon_price.total_emissions_tco2e


def test_balanced_mode_with_zero_carbon_price_matches_cost_mode(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    balanced = solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=0.0)
    cost = solve(problem, ObjectiveMode.COST)

    assert balanced.total_cost_usd == pytest.approx(cost.total_cost_usd)
    assert balanced.total_emissions_tco2e == pytest.approx(cost.total_emissions_tco2e)


# --- Trade-offs stay visible --------------------------------------------------------


def test_emissions_mode_can_increase_cost_and_reports_it_negatively(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Minimizing emissions can cost more; a negative saving must stay visible."""
    problem = build_problem(
        hours=HOURS,
        prices=DIRTY_CHEAP,
        carbons=DIRTY_CHEAP_CARBONS,
        workloads=[JOB],
    )
    result = solve(problem, ObjectiveMode.EMISSIONS)

    assert result.cost_savings_pct is not None
    assert result.cost_savings_pct < 0
    assert result.emissions_reduction_pct is not None
    assert result.emissions_reduction_pct > 0


def test_cost_mode_can_increase_emissions_and_reports_it_negatively(build_problem) -> None:  # type: ignore[no-untyped-def]
    prices = [100.0] * 6 + [10.0] * 18
    carbons = [0.1] * 6 + [1.0] * 18
    problem = build_problem(
        hours=HOURS,
        prices=prices,
        carbons=carbons,
        workloads=[JOB],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.emissions_reduction_pct is not None
    assert result.emissions_reduction_pct < 0
    assert result.cost_savings_pct is not None
    assert result.cost_savings_pct > 0


def test_savings_are_none_when_the_baseline_cost_is_zero(build_problem) -> None:  # type: ignore[no-untyped-def]
    """A percentage of zero is undefined; reporting 0% would be a false claim."""
    problem = build_problem(hours=4, prices=[0.0] * 4, loads=[0.0] * 4, capacities=[10.0] * 4)
    result = solve(problem, ObjectiveMode.COST)

    assert result.baseline_total_cost_usd == pytest.approx(0.0)
    assert result.cost_savings_pct is None


# --- Reporting completeness ---------------------------------------------------------


@pytest.mark.parametrize("mode", list(ObjectiveMode))
def test_every_mode_reports_cost_and_emissions_separately(build_problem, mode) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    result = solve(problem, mode, carbon_price_usd_per_tco2e=25.0)

    assert result.status.value == "optimal"
    assert result.total_cost_usd > 0
    assert result.total_emissions_tco2e > 0
    assert result.hourly
    assert result.baseline_total_cost_usd is not None
    assert result.baseline_total_emissions_tco2e is not None


def test_result_carries_assumptions_and_diagnostics(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=HOURS, prices=CHEAP_LATE_PRICES, workloads=[JOB])
    result = solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=30.0)

    assert result.diagnostics.solver.startswith("scipy")
    assert result.diagnostics.variables == 24
    assert result.diagnostics.constraints == 25
    assert result.diagnostics.solve_seconds >= 0
    for assumption in ASSUMPTIONS:
        assert assumption in result.assumptions
    assert any("30" in assumption for assumption in result.assumptions)


def test_hourly_points_line_up_with_the_horizon(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=HOURS, prices=CHEAP_LATE_PRICES, workloads=[JOB])
    result = solve(problem, ObjectiveMode.COST)

    assert len(result.hourly) == HOURS
    for index, point in enumerate(result.hourly):
        assert point.hour == index
        assert point.timestamp_utc == problem.timestamps_utc[index]
        assert point.optimized_cost_usd == pytest.approx(
            point.price_usd_per_mwh * point.optimized_consumption_mwh
        )


def test_reported_totals_match_the_sum_of_hourly_points(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.total_cost_usd == pytest.approx(
        sum(point.optimized_cost_usd for point in result.hourly)
    )
    assert result.total_emissions_tco2e == pytest.approx(
        sum(point.optimized_emissions_tco2e for point in result.hourly)
    )


def test_multi_job_schedule_satisfies_all_constraints(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(
        hours=HOURS,
        prices=CHEAP_LATE_PRICES,
        carbons=CHEAP_LATE_CARBONS,
        loads=[14.0] * HOURS,
        capacities=[34.0] * HOURS,
        workloads=[
            ("train", 70.0, 0, 23, 9.0),
            ("infer", 45.0, 8, 23, 7.0),
            ("backup", 20.0, 0, 6, 5.0),
        ],
    )
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "optimal"
    assert result.constraint_violations == ()
    # One variable per job per hour inside that job's window: 24 + 16 + 7.
    assert result.diagnostics.variables == 47
    assert result.diagnostics.constraints == 3 + HOURS


def test_negative_carbon_price_is_rejected(build_problem) -> None:  # type: ignore[no-untyped-def]
    problem = build_problem(hours=4)
    with pytest.raises(ValueError, match="non-negative"):
        solve(problem, ObjectiveMode.BALANCED, carbon_price_usd_per_tco2e=-1.0)


def test_solver_is_reproducible(build_problem) -> None:  # type: ignore[no-untyped-def]
    """Identical inputs must produce equivalent results."""
    problem = build_problem(
        hours=HOURS, prices=CHEAP_LATE_PRICES, carbons=CHEAP_LATE_CARBONS, workloads=[JOB]
    )
    first = solve(problem, ObjectiveMode.COST)
    second = solve(problem, ObjectiveMode.COST)

    assert first.total_cost_usd == pytest.approx(second.total_cost_usd)
    assert first.job_allocations == second.job_allocations


def test_post_solve_verification_downgrades_a_bad_solution(
    build_problem,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    """A solver answer that breaks a hard constraint must never be presented as usable."""
    monkeypatch.setattr(
        "app.optimization.solver.Schedule.constraint_violations",
        lambda self, tolerance=1e-6: ["Hour 0 consumes 999 MWh, above the 40 MWh capacity."],
    )
    problem = build_problem(hours=4, workloads=[("a", 10.0, 0, 3, 5.0)])
    result = solve(problem, ObjectiveMode.COST)

    assert result.status.value == "numerical_error"
    assert "post-solve constraint verification" in result.diagnostics.message
    assert result.constraint_violations
    assert any("violates a hard constraint" in note for note in result.assumptions)
