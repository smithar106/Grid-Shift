"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata``, which is what Alembic
autogeneration and ``create_all`` rely on.
"""

from app.models.base import Base
from app.models.dataset import Dataset, HourlyObservation
from app.models.facility import Facility
from app.models.scenario import (
    HourlyAllocation,
    OptimizationResultRecord,
    Scenario,
    ScenarioWorkload,
)

__all__ = [
    "Base",
    "Dataset",
    "Facility",
    "HourlyAllocation",
    "HourlyObservation",
    "OptimizationResultRecord",
    "Scenario",
    "ScenarioWorkload",
]
