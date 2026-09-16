"""Scenarios, their workloads, and the results of optimizing them.

A scenario is the unit of reproducibility. It records which datasets were used, the
objective, the carbon price, and the workloads — everything needed to re-derive the
result. The archived ``snapshot_checksum`` is the fingerprint of that input set.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import UtcDateTime, utcnow

__all__ = [
    "HourlyAllocation",
    "OptimizationResultRecord",
    "Scenario",
    "ScenarioWorkload",
]


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(String(20))
    carbon_price_usd_per_tco2e: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="draft")

    #: Dataset ids that formed the input snapshot, and its combined fingerprint.
    dataset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    snapshot_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    workloads: Mapped[list[ScenarioWorkload]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    results: Mapped[list[OptimizationResultRecord]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OptimizationResultRecord.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Scenario {self.name} objective={self.objective} status={self.status}>"


class ScenarioWorkload(Base):
    """A job to be scheduled. Hours are indices into the scenario's horizon."""

    __tablename__ = "workloads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )

    job_id: Mapped[str] = mapped_column(String(100))
    energy_mwh: Mapped[float]
    release_hour: Mapped[int] = mapped_column(Integer)
    deadline_hour: Mapped[int] = mapped_column(Integer)
    max_mw: Mapped[float]

    scenario: Mapped[Scenario] = relationship(back_populates="workloads")

    def __repr__(self) -> str:
        return f"<ScenarioWorkload {self.job_id} {self.energy_mwh}MWh>"


class OptimizationResultRecord(Base):
    """One solve. Keeps the solver's own status and every reported quantity."""

    __tablename__ = "optimization_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )

    solver_status: Mapped[str] = mapped_column(String(30))
    solver_message: Mapped[str] = mapped_column(String(500), default="")
    solver: Mapped[str] = mapped_column(String(100), default="")
    solve_seconds: Mapped[float] = mapped_column(default=0.0)
    variables: Mapped[int] = mapped_column(Integer, default=0)
    constraints: Mapped[int] = mapped_column(Integer, default=0)

    objective_value: Mapped[float] = mapped_column(default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(default=0.0)
    total_emissions_tco2e: Mapped[float] = mapped_column(default=0.0)
    baseline_total_cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    baseline_total_emissions_tco2e: Mapped[float | None] = mapped_column(nullable=True)
    cost_savings_pct: Mapped[float | None] = mapped_column(nullable=True)
    emissions_reduction_pct: Mapped[float | None] = mapped_column(nullable=True)

    #: Derived hourly series (fixed load, flexible, totals, prices, carbon).
    hourly: Mapped[list[dict]] = mapped_column(JSON, default=list)
    #: Baseline per-job allocation, kept so the comparison is inspectable.
    baseline_allocations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraint_violations: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    scenario: Mapped[Scenario] = relationship(back_populates="results")
    allocations: Mapped[list[HourlyAllocation]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<OptimizationResult {self.id} status={self.solver_status}>"


class HourlyAllocation(Base):
    """Energy assigned to one job in one hour of the optimized schedule."""

    __tablename__ = "hourly_allocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("optimization_results.id", ondelete="CASCADE"), index=True
    )

    job_id: Mapped[str] = mapped_column(String(100))
    timestamp_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    energy_mwh: Mapped[float]

    result: Mapped[OptimizationResultRecord] = relationship(back_populates="allocations")

    def __repr__(self) -> str:
        return (
            f"<HourlyAllocation {self.job_id}@{self.timestamp_utc.isoformat()} {self.energy_mwh}>"
        )
