"""A concrete workload schedule, plus the arithmetic that judges it.

Both the optimizer and the baseline produce a ``Schedule``, so their cost and emissions
are computed by exactly the same code. That is what makes the comparison meaningful: if
the two used different accounting, a saving could be an artifact of the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.optimization.problem import OptimizationProblem

__all__ = ["TOLERANCE", "Schedule"]

#: Numerical slack for constraint checks. HiGHS works in floating point, so equality
#: constraints are satisfied to within a small tolerance rather than exactly.
TOLERANCE = 1e-6


@dataclass(frozen=True)
class Schedule:
    """Energy allocated to each job in each hour, alongside the problem it answers."""

    problem: OptimizationProblem
    allocations: dict[str, tuple[float, ...]]
    label: str = "schedule"

    @property
    def interval_hours(self) -> float:
        return self.problem.interval_hours

    @property
    def flexible_mwh(self) -> tuple[float, ...]:
        """Total flexible energy scheduled in each hour."""
        horizon = self.problem.horizon_hours
        totals = [0.0] * horizon
        for per_hour in self.allocations.values():
            for hour in range(horizon):
                totals[hour] += per_hour[hour]
        return tuple(totals)

    @property
    def consumption_mwh(self) -> tuple[float, ...]:
        """Total facility consumption (fixed plus flexible) in each hour."""
        return tuple(
            base + flexible
            for base, flexible in zip(
                self.problem.baseline_load_mwh, self.flexible_mwh, strict=True
            )
        )

    @property
    def cost_usd(self) -> float:
        return sum(
            price * consumption
            for price, consumption in zip(
                self.problem.price_usd_per_mwh, self.consumption_mwh, strict=True
            )
        )

    @property
    def emissions_tco2e(self) -> float:
        return sum(
            carbon * consumption
            for carbon, consumption in zip(
                self.problem.carbon_tco2e_per_mwh, self.consumption_mwh, strict=True
            )
        )

    @property
    def job_totals(self) -> dict[str, float]:
        return {job_id: sum(per_hour) for job_id, per_hour in self.allocations.items()}

    def constraint_violations(self, tolerance: float = TOLERANCE) -> list[str]:
        """Return human-readable descriptions of every violated hard constraint."""
        violations: list[str] = []
        horizon = self.problem.horizon_hours
        interval = self.interval_hours
        lengths_ok = True

        by_id = {workload.job_id: workload for workload in self.problem.workloads}

        for job_id, per_hour in self.allocations.items():
            workload = by_id.get(job_id)
            if workload is None:
                violations.append(f"Schedule contains unknown job {job_id!r}.")
                continue
            if len(per_hour) != horizon:
                lengths_ok = False
                violations.append(
                    f"Job {job_id!r} has {len(per_hour)} hourly values but the horizon "
                    f"is {horizon}."
                )
                continue

            total = sum(per_hour)
            if abs(total - workload.energy_mwh) > tolerance * max(1.0, workload.energy_mwh):
                violations.append(
                    f"Job {job_id!r} completes {total:.6f} MWh but requires "
                    f"{workload.energy_mwh:.6f} MWh."
                )

            for hour, energy in enumerate(per_hour):
                if energy < -tolerance:
                    violations.append(
                        f"Job {job_id!r} has negative energy {energy:.6f} in hour {hour}."
                    )
                if energy > workload.max_mw * interval + tolerance:
                    violations.append(
                        f"Job {job_id!r} draws {energy:.6f} MWh in hour {hour}, above its "
                        f"{workload.max_mw * interval:.6f} MWh limit."
                    )
                outside_window = not (workload.release_hour <= hour <= workload.deadline_hour)
                if outside_window and abs(energy) > tolerance:
                    violations.append(
                        f"Job {job_id!r} runs in hour {hour}, outside its window "
                        f"[{workload.release_hour}, {workload.deadline_hour}]."
                    )

        if lengths_ok:
            for hour, consumption in enumerate(self.consumption_mwh):
                limit = self.problem.capacity_mw[hour] * interval
                if consumption > limit + tolerance:
                    violations.append(
                        f"Hour {hour} consumes {consumption:.6f} MWh, above the "
                        f"{limit:.6f} MWh capacity."
                    )

        return violations

    def assert_valid(self, tolerance: float = TOLERANCE) -> None:
        violations = self.constraint_violations(tolerance)
        if violations:
            raise AssertionError(f"{self.label} violates constraints: " + "; ".join(violations))
