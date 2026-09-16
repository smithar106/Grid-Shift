"""Shared builders for optimization tests.

Problems are constructed explicitly in every test rather than hidden behind defaults,
because the whole point of these tests is to pin down the arithmetic.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from app.optimization.problem import OptimizationProblem, Workload

START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def make_timestamps(hours: int, start: datetime = START) -> tuple[datetime, ...]:
    return tuple(start + timedelta(hours=index) for index in range(hours))


def workload_specs(
    specs: Sequence[tuple[str, float, int, int, float]],
) -> tuple[Workload, ...]:
    """Build workloads from ``(job_id, energy_mwh, release, deadline, max_mw)`` tuples."""
    return tuple(
        Workload(
            job_id=job_id,
            energy_mwh=energy,
            release_hour=release,
            deadline_hour=deadline,
            max_mw=max_mw,
        )
        for job_id, energy, release, deadline, max_mw in specs
    )


@pytest.fixture
def build_problem() -> Callable[..., OptimizationProblem]:
    """Factory for problems with sensible, explicit shapes."""

    def _build(
        *,
        hours: int = 24,
        prices: Sequence[float] | None = None,
        carbons: Sequence[float] | None = None,
        loads: Sequence[float] | None = None,
        capacities: Sequence[float] | None = None,
        workloads: Sequence[tuple[str, float, int, int, float]] = (),
        start: datetime = START,
        location_id: str = "facility_001",
    ) -> OptimizationProblem:
        return OptimizationProblem(
            location_id=location_id,
            timestamps_utc=make_timestamps(hours, start),
            price_usd_per_mwh=tuple(prices if prices is not None else [50.0] * hours),
            carbon_tco2e_per_mwh=tuple(carbons if carbons is not None else [0.5] * hours),
            baseline_load_mwh=tuple(loads if loads is not None else [10.0] * hours),
            capacity_mw=tuple(capacities if capacities is not None else [40.0] * hours),
            workloads=workload_specs(workloads),
        )

    return _build
