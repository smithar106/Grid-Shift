"""Assembling a solvable problem from stored datasets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.dataset import Dataset, HourlyObservation
from app.models.facility import Facility
from app.models.scenario import ScenarioWorkload
from app.schemas.enums import CANONICAL_UNITS, Metric
from app.services.scenario_builder import ScenarioBuildError, build_problem

START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def make_facility(capacity_mw: float = 40.0) -> Facility:
    return Facility(
        id=uuid4(),
        name="Test Facility",
        location_id="facility_001",
        timezone="UTC",
        capacity_mw=capacity_mw,
    )


def make_dataset(
    metric_values: dict[Metric, list[float]],
    *,
    checksum: str = "a" * 64,
    start: datetime = START,
    skip_hours: set[int] | None = None,
) -> Dataset:
    dataset = Dataset(
        id=uuid4(),
        source="uploaded_csv",
        data_status="user_supplied",
        metrics=",".join(sorted(metric.value for metric in metric_values)),
        retrieved_at=start,
        checksum=checksum,
    )
    skipped = skip_hours or set()
    for metric, values in metric_values.items():
        unit = CANONICAL_UNITS[metric]
        for index, value in enumerate(values):
            if index in skipped:
                continue
            dataset.observations.append(
                HourlyObservation(
                    timestamp_utc=start + timedelta(hours=index),
                    location_id="facility_001",
                    metric=metric.value,
                    value=value,
                    unit=unit.value,
                    source="uploaded_csv",
                    data_status="user_supplied",
                    retrieved_at=start,
                    original_timestamp="",
                    original_timezone="UTC",
                    original_value=value,
                    original_unit=unit.value,
                )
            )
    return dataset


def make_workload(
    job_id: str = "batch", energy: float = 120.0, release: int = 0, deadline: int = 23
) -> ScenarioWorkload:
    return ScenarioWorkload(
        id=uuid4(),
        job_id=job_id,
        energy_mwh=energy,
        release_hour=release,
        deadline_hour=deadline,
        max_mw=20.0,
    )


def full_dataset(checksum: str = "a" * 64, hours: int = 24) -> Dataset:
    return make_dataset(
        {
            Metric.ELECTRICITY_PRICE: [50.0] * hours,
            Metric.CARBON_INTENSITY: [0.4] * hours,
            Metric.FACILITY_LOAD: [10.0] * hours,
        },
        checksum=checksum,
    )


def test_builds_a_problem_with_aligned_series() -> None:
    built = build_problem(make_facility(), [full_dataset()], [make_workload()])

    assert built.problem.horizon_hours == 24
    assert built.problem.price_usd_per_mwh == (50.0,) * 24
    assert built.problem.carbon_tco2e_per_mwh == (0.4,) * 24
    assert built.problem.baseline_load_mwh == (10.0,) * 24
    assert built.problem.capacity_mw == (40.0,) * 24
    assert built.problem.location_id == "facility_001"
    assert [w.job_id for w in built.problem.workloads] == ["batch"]
    assert built.horizon_start == START
    assert built.horizon_end == START + timedelta(hours=23)


def test_records_which_dataset_supplied_each_metric() -> None:
    dataset = full_dataset()
    built = build_problem(make_facility(), [dataset], [make_workload()])

    assert set(built.datasets_used) == {
        Metric.ELECTRICITY_PRICE,
        Metric.CARBON_INTENSITY,
        Metric.FACILITY_LOAD,
    }
    assert set(built.datasets_used.values()) == {str(dataset.id)}


def test_no_datasets_is_an_actionable_error() -> None:
    with pytest.raises(ScenarioBuildError, match="no datasets"):
        build_problem(make_facility(), [], [make_workload()])


def test_missing_carbon_intensity_is_reported() -> None:
    dataset = make_dataset({Metric.ELECTRICITY_PRICE: [50.0] * 24})
    with pytest.raises(ScenarioBuildError, match="carbon_intensity"):
        build_problem(make_facility(), [dataset], [make_workload()])


def test_missing_electricity_price_is_reported() -> None:
    dataset = make_dataset({Metric.CARBON_INTENSITY: [0.4] * 24})
    with pytest.raises(ScenarioBuildError, match="electricity_price"):
        build_problem(make_facility(), [dataset], [make_workload()])


def test_ambiguous_metric_across_two_datasets_is_rejected() -> None:
    """The builder must not silently pick one of two competing price series."""
    first = make_dataset(
        {Metric.ELECTRICITY_PRICE: [50.0] * 24, Metric.CARBON_INTENSITY: [0.4] * 24},
        checksum="a" * 64,
    )
    second = make_dataset({Metric.ELECTRICITY_PRICE: [60.0] * 24}, checksum="b" * 64)

    with pytest.raises(ScenarioBuildError, match="more than one dataset"):
        build_problem(make_facility(), [first, second], [make_workload()])


def test_series_that_do_not_overlap_are_rejected() -> None:
    prices = make_dataset({Metric.ELECTRICITY_PRICE: [50.0] * 24}, checksum="a" * 64)
    carbons = make_dataset(
        {Metric.CARBON_INTENSITY: [0.4] * 24},
        checksum="b" * 64,
        start=START + timedelta(days=3),
    )

    with pytest.raises(ScenarioBuildError, match="do not overlap"):
        build_problem(make_facility(), [prices, carbons], [make_workload()])


def test_horizon_is_the_intersection_of_the_series() -> None:
    prices = make_dataset({Metric.ELECTRICITY_PRICE: [50.0] * 24}, checksum="a" * 64)
    carbons = make_dataset(
        {Metric.CARBON_INTENSITY: [0.4] * 12},
        checksum="b" * 64,
        start=START + timedelta(hours=6),
    )

    built = build_problem(make_facility(), [prices, carbons], [])
    assert built.problem.horizon_hours == 12
    assert built.horizon_start == START + timedelta(hours=6)


def test_a_gap_inside_the_shared_horizon_is_rejected() -> None:
    """Ingestion prevents gaps, but the builder must not trust that."""
    prices = make_dataset({Metric.ELECTRICITY_PRICE: [50.0] * 24}, checksum="a" * 64)
    carbons = make_dataset({Metric.CARBON_INTENSITY: [0.4] * 24}, checksum="b" * 64, skip_hours={7})

    with pytest.raises(ScenarioBuildError, match="missing"):
        build_problem(make_facility(), [prices, carbons], [])


def test_missing_facility_load_defaults_to_zero_and_says_so() -> None:
    dataset = make_dataset(
        {Metric.ELECTRICITY_PRICE: [50.0] * 24, Metric.CARBON_INTENSITY: [0.4] * 24}
    )
    built = build_problem(make_facility(), [dataset], [])

    assert built.problem.baseline_load_mwh == (0.0,) * 24
    assert any("baseline load" in note for note in built.assumptions)


def test_capacity_assumption_is_recorded() -> None:
    built = build_problem(make_facility(capacity_mw=33.0), [full_dataset()], [])
    assert any("33" in note for note in built.assumptions)


def test_deadline_beyond_the_horizon_is_rejected() -> None:
    with pytest.raises(ScenarioBuildError, match="deadline_hour"):
        build_problem(make_facility(), [full_dataset()], [make_workload(deadline=99)])


def test_workloads_are_converted_to_domain_objects() -> None:
    built = build_problem(
        make_facility(),
        [full_dataset()],
        [make_workload("a", 40.0, 2, 10), make_workload("b", 15.0, 0, 5)],
    )

    workloads = {w.job_id: w for w in built.problem.workloads}
    assert workloads["a"].energy_mwh == 40.0
    assert workloads["a"].window_hours == 9
    assert workloads["b"].release_hour == 0


def test_snapshot_checksum_is_order_independent() -> None:
    prices = make_dataset({Metric.ELECTRICITY_PRICE: [50.0] * 24}, checksum="a" * 64)
    carbons = make_dataset({Metric.CARBON_INTENSITY: [0.4] * 24}, checksum="b" * 64)

    forward = build_problem(make_facility(), [prices, carbons], [])
    backward = build_problem(make_facility(), [carbons, prices], [])

    assert forward.snapshot_checksum == backward.snapshot_checksum


def test_snapshot_checksum_changes_with_content() -> None:
    first = build_problem(make_facility(), [full_dataset(checksum="a" * 64)], [])
    second = build_problem(make_facility(), [full_dataset(checksum="c" * 64)], [])
    assert first.snapshot_checksum != second.snapshot_checksum
