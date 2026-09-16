"""Validation issues and ingestion reports.

Failures are collected rather than raised one at a time, so a user uploading a 72-row
CSV sees every problem in one response instead of fixing them serially.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import DataSource, DataStatus, Metric, Unit

__all__ = [
    "DatasetValidationError",
    "IngestionIssue",
    "IngestionReport",
    "IssueCode",
    "IssueSeverity",
    "SeriesSummary",
]


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class IssueCode(StrEnum):
    EMPTY_DATASET = "empty_dataset"
    MISSING_COLUMN = "missing_column"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    UNKNOWN_METRIC = "unknown_metric"
    UNKNOWN_UNIT = "unknown_unit"
    INCOMPATIBLE_UNIT = "incompatible_unit"
    INVALID_VALUE = "invalid_value"
    NEGATIVE_VALUE = "negative_value"
    INVALID_TIMESTAMP = "invalid_timestamp"
    AMBIGUOUS_TIMESTAMP = "ambiguous_timestamp"
    NONEXISTENT_TIMESTAMP = "nonexistent_timestamp"
    MISSING_TIMEZONE = "missing_timezone"
    DUPLICATE_HOUR = "duplicate_hour"
    MISSING_HOUR = "missing_hour"
    CURRENCY_MISMATCH = "currency_mismatch"
    MIXED_SOURCE = "mixed_source"


class IngestionIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: IssueSeverity
    code: IssueCode
    message: str
    row: int | None = None
    column: str | None = None

    def __str__(self) -> str:
        location = f"row {self.row}" if self.row is not None else "dataset"
        if self.column:
            location = f"{location}, column {self.column!r}"
        return f"[{self.severity}] {self.code} ({location}): {self.message}"


class SeriesSummary(BaseModel):
    """Aggregate view of one metric in a validated dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: Metric
    unit: Unit
    hours: int = Field(ge=0)
    start_utc: datetime
    end_utc: datetime
    minimum: float
    maximum: float
    total: float
    is_contiguous: bool


class IngestionReport(BaseModel):
    """What the ingestion service produced, including everything it had to reject."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: UUID
    source: DataSource
    data_status: DataStatus
    retrieved_at: datetime
    checksum: str
    rows_read: int = Field(ge=0)
    rows_accepted: int = Field(ge=0)
    series: tuple[SeriesSummary, ...]
    warnings: tuple[IngestionIssue, ...] = ()


class DatasetValidationError(ValueError):
    """Raised when a dataset cannot be accepted.

    Carries every issue found so the caller can present them together.
    """

    def __init__(self, issues: list[IngestionIssue]) -> None:
        self.issues = tuple(issues)
        errors = [issue for issue in self.issues if issue.severity is IssueSeverity.ERROR]
        summary = f"{len(errors)} validation error(s)"
        detail = "; ".join(str(issue) for issue in errors[:5])
        if len(errors) > 5:
            detail += f"; and {len(errors) - 5} more"
        super().__init__(f"{summary}: {detail}" if detail else summary)
