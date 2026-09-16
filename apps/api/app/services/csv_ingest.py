"""CSV ingestion and validation.

The pipeline is deliberately strict. GridShift's central design principle is that every
recommendation is traceable to its input data, so this module would rather reject a file
than guess at a timezone, coerce a bad number, or fill a missing hour.

Validation collects every issue it finds and raises once, so the caller can report all
problems at the same time.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any
from uuid import UUID, uuid4

from app.schemas.enums import (
    CANONICAL_UNITS,
    CURRENCY_METRICS,
    METRIC_UNITS,
    NON_NEGATIVE_METRICS,
    UNIT_SCALE,
    DataSource,
    DataStatus,
    Metric,
    Unit,
)
from app.schemas.ingestion import (
    DatasetValidationError,
    IngestionIssue,
    IngestionReport,
    IssueCode,
    IssueSeverity,
    SeriesSummary,
)
from app.schemas.observations import Observation, ObservationSeries
from app.services.timeutil import (
    TimezoneResolutionError,
    classify_local_time,
    parse_timestamp,
    resolve_zone,
)

__all__ = ["IngestedDataset", "ingest_csv", "ingest_csv_bytes"]


# --- Column and value aliases -------------------------------------------------------
# Users should not have to read the source to produce a valid file, so common spellings
# are accepted. Everything is normalized to lowercase with separators removed.

TIMESTAMP_COLUMNS = ("timestamp", "timestamputc", "datetime", "time")
METRIC_COLUMNS = ("metric", "type")
VALUE_COLUMNS = ("value", "amount")
UNIT_COLUMNS = ("unit", "units")
LOCATION_COLUMNS = ("locationid", "location", "facilityid", "siteid")
TIMEZONE_COLUMNS = ("timezone", "tz", "timezoneid")

METRIC_ALIASES = {
    "electricityprice": Metric.ELECTRICITY_PRICE,
    "price": Metric.ELECTRICITY_PRICE,
    "powerprice": Metric.ELECTRICITY_PRICE,
    "carbonintensity": Metric.CARBON_INTENSITY,
    "carbon": Metric.CARBON_INTENSITY,
    "carbonfactor": Metric.CARBON_INTENSITY,
    "emissionsfactor": Metric.CARBON_INTENSITY,
    "emissionfactor": Metric.CARBON_INTENSITY,
    "facilityload": Metric.FACILITY_LOAD,
    "load": Metric.FACILITY_LOAD,
    "baselineload": Metric.FACILITY_LOAD,
    "temperature": Metric.TEMPERATURE,
    "temp": Metric.TEMPERATURE,
    "relativehumidity": Metric.RELATIVE_HUMIDITY,
    "humidity": Metric.RELATIVE_HUMIDITY,
}

UNIT_ALIASES = {
    "usd/mwh": Unit.USD_PER_MWH,
    "$/mwh": Unit.USD_PER_MWH,
    "usdpermwh": Unit.USD_PER_MWH,
    "eur/mwh": Unit.EUR_PER_MWH,
    "€/mwh": Unit.EUR_PER_MWH,
    "gbp/mwh": Unit.GBP_PER_MWH,
    "£/mwh": Unit.GBP_PER_MWH,
    "tco2e/mwh": Unit.TONNES_CO2E_PER_MWH,
    "t/mwh": Unit.TONNES_CO2E_PER_MWH,
    "tonnes/mwh": Unit.TONNES_CO2E_PER_MWH,
    "tonnesco2e/mwh": Unit.TONNES_CO2E_PER_MWH,
    "kgco2e/mwh": Unit.KG_CO2E_PER_MWH,
    "kg/mwh": Unit.KG_CO2E_PER_MWH,
    "mwh": Unit.MWH,
    "kwh": Unit.KWH,
    "degc": Unit.CELSIUS,
    "°c": Unit.CELSIUS,
    "c": Unit.CELSIUS,
    "celsius": Unit.CELSIUS,
    "%": Unit.PERCENT,
    "percent": Unit.PERCENT,
}

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class IngestedDataset:
    """A validated dataset: canonical series plus the report describing the parse."""

    dataset_id: UUID
    source: DataSource
    data_status: DataStatus
    retrieved_at: datetime
    checksum: str
    series: dict[Metric, ObservationSeries]
    report: IngestionReport

    def require(self, metric: Metric) -> ObservationSeries:
        """Return a metric's series or raise, naming what is missing."""
        try:
            return self.series[metric]
        except KeyError:
            available = ", ".join(sorted(m.value for m in self.series)) or "none"
            raise DatasetValidationError(
                [
                    IngestionIssue(
                        severity=IssueSeverity.ERROR,
                        code=IssueCode.MISSING_COLUMN,
                        message=(
                            f"Dataset does not contain {metric.value}. "
                            f"Available metrics: {available}."
                        ),
                    )
                ]
            ) from None


def _normalize_key(text: str) -> str:
    """Lowercase and drop separators so 'location_id', 'Location ID' and 'locationid'
    all collapse to the same key. Symbols such as '/', '%' and currency signs are kept
    because they are significant in unit names."""
    return "".join(char for char in text.strip().lower() if char not in " _-")


def _resolve_columns(fieldnames: list[str], issues: list[IngestionIssue]) -> dict[str, str]:
    """Map logical column names to the header spellings actually present."""
    by_key: dict[str, str] = {}
    for field in fieldnames:
        by_key.setdefault(_normalize_key(field), field)

    resolved: dict[str, str] = {}
    for logical, candidates in (
        ("timestamp", TIMESTAMP_COLUMNS),
        ("metric", METRIC_COLUMNS),
        ("value", VALUE_COLUMNS),
        ("unit", UNIT_COLUMNS),
        ("location", LOCATION_COLUMNS),
        ("timezone", TIMEZONE_COLUMNS),
    ):
        for candidate in candidates:
            if candidate in by_key:
                resolved[logical] = by_key[candidate]
                break

    for required in ("timestamp", "metric", "value", "unit"):
        if required not in resolved:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.MISSING_COLUMN,
                    message=(
                        f"Required column for {required!r} was not found. "
                        f"Expected one of: {', '.join(candidates_for(required))}."
                    ),
                )
            )
    return resolved


def candidates_for(logical: str) -> tuple[str, ...]:
    return {
        "timestamp": TIMESTAMP_COLUMNS,
        "metric": METRIC_COLUMNS,
        "value": VALUE_COLUMNS,
        "unit": UNIT_COLUMNS,
        "location": LOCATION_COLUMNS,
        "timezone": TIMEZONE_COLUMNS,
    }[logical]


def _parse_metric(raw: str) -> Metric | None:
    key = _normalize_key(raw)
    if key in METRIC_ALIASES:
        return METRIC_ALIASES[key]
    try:
        return Metric(raw.strip())
    except ValueError:
        return None


def _parse_unit(raw: str) -> Unit | None:
    text = raw.strip()
    key = _normalize_key(text)
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    try:
        return Unit(text)
    except ValueError:
        return None


def _parse_value(raw: str) -> float | None:
    try:
        parsed = float(raw.strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _canonicalize(value: float, unit: Unit, metric: Metric) -> tuple[float, Unit]:
    scale = UNIT_SCALE.get(unit, 1.0)
    return value * scale, CANONICAL_UNITS[metric]


def _checksum(
    series: dict[Metric, ObservationSeries],
    *,
    source: DataSource,
    data_status: DataStatus,
) -> str:
    """Hash the canonical content so an identical snapshot is provably identical."""
    digest = hashlib.sha256()
    digest.update(f"{source.value}|{data_status.value}\n".encode())
    for metric in sorted(series, key=lambda item: item.value):
        current = series[metric]
        digest.update(f"{current.location_id}|{metric.value}|{current.unit.value}\n".encode())
        for observation in current.observations:
            digest.update(
                f"{observation.timestamp_utc.isoformat()}|{observation.value!r}\n".encode()
            )
    return digest.hexdigest()


def _dedupe_and_check_gaps(
    observations: list[Observation],
    *,
    metric: Metric,
    allow_gaps: bool,
    issues: list[IngestionIssue],
) -> tuple[list[Observation], bool, tuple[datetime, ...]]:
    ordered = sorted(observations, key=lambda item: item.timestamp_utc)

    unique: list[Observation] = []
    seen: set[datetime] = set()
    for observation in ordered:
        if observation.timestamp_utc in seen:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.DUPLICATE_HOUR,
                    message=(
                        f"{metric.value} has more than one observation for "
                        f"{observation.timestamp_utc.isoformat()}."
                    ),
                )
            )
            continue
        seen.add(observation.timestamp_utc)
        unique.append(observation)

    gaps: list[datetime] = []
    for previous, current in pairwise(unique):
        delta = current.timestamp_utc - previous.timestamp_utc
        if delta == HOUR:
            continue
        if delta < HOUR:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.DUPLICATE_HOUR,
                    message=(
                        f"{metric.value} has observations {delta} apart at "
                        f"{current.timestamp_utc.isoformat()}; hourly data is required."
                    ),
                )
            )
            continue
        missing = previous.timestamp_utc + HOUR
        while missing < current.timestamp_utc:
            gaps.append(missing)
            missing += HOUR

    severity = IssueSeverity.WARNING if allow_gaps else IssueSeverity.ERROR
    for gap in gaps:
        issues.append(
            IngestionIssue(
                severity=severity,
                code=IssueCode.MISSING_HOUR,
                message=(
                    f"{metric.value} is missing {gap.isoformat()}. "
                    + (
                        "Accepted because gaps were explicitly allowed."
                        if allow_gaps
                        else "Upload a complete hourly series."
                    )
                ),
            )
        )

    return unique, not gaps, tuple(gaps)


def ingest_csv(
    text: str,
    *,
    default_location_id: str = "facility_001",
    default_timezone: str | None = None,
    source: DataSource = DataSource.UPLOADED_CSV,
    data_status: DataStatus = DataStatus.USER_SUPPLIED,
    allow_gaps: bool = False,
    max_rows: int = 20_000,
    dataset_id: UUID | None = None,
    retrieved_at: datetime | None = None,
) -> IngestedDataset:
    """Parse, validate, and canonicalize an hourly CSV.

    Raises:
        DatasetValidationError: if any row or the resulting series is invalid.
    """
    issues: list[IngestionIssue] = []
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [name for name in (reader.fieldnames or []) if name is not None]

    if not fieldnames:
        raise DatasetValidationError(
            [
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.EMPTY_DATASET,
                    message="The file has no header row.",
                )
            ]
        )

    columns = _resolve_columns(fieldnames, issues)
    if issues:
        raise DatasetValidationError(issues)

    timestamp_column = columns["timestamp"]
    metric_column = columns["metric"]
    value_column = columns["value"]
    unit_column = columns["unit"]
    location_column = columns.get("location")
    timezone_column = columns.get("timezone")

    rows = list(reader)
    if not rows:
        raise DatasetValidationError(
            [
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.EMPTY_DATASET,
                    message="The file has a header but no data rows.",
                )
            ]
        )
    if len(rows) > max_rows:
        raise DatasetValidationError(
            [
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.ROW_LIMIT_EXCEEDED,
                    message=f"File has {len(rows)} rows; the limit is {max_rows}.",
                )
            ]
        )

    observations: list[Observation] = []
    ambiguous_occurrences: dict[tuple[str, datetime], int] = {}
    accepted = 0

    for offset, row in enumerate(rows, start=2):
        row_issues_before = len(issues)

        raw_metric = (row.get(metric_column) or "").strip()
        metric = _parse_metric(raw_metric)
        if metric is None:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.UNKNOWN_METRIC,
                    message=f"Unrecognized metric {raw_metric!r}.",
                    row=offset,
                    column=metric_column,
                )
            )

        raw_unit = (row.get(unit_column) or "").strip()
        unit = _parse_unit(raw_unit)
        if unit is None:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.UNKNOWN_UNIT,
                    message=f"Unrecognized unit {raw_unit!r}.",
                    row=offset,
                    column=unit_column,
                )
            )

        if metric is not None and unit is not None and unit not in METRIC_UNITS[metric]:
            allowed = ", ".join(sorted(item.value for item in METRIC_UNITS[metric]))
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.INCOMPATIBLE_UNIT,
                    message=(
                        f"Unit {unit.value!r} is not valid for {metric.value}. "
                        f"Expected one of: {allowed}."
                    ),
                    row=offset,
                    column=unit_column,
                )
            )

        raw_value = (row.get(value_column) or "").strip()
        value = _parse_value(raw_value)
        if value is None:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.INVALID_VALUE,
                    message=f"Value {raw_value!r} is not a finite number.",
                    row=offset,
                    column=value_column,
                )
            )
        elif metric is not None and metric in NON_NEGATIVE_METRICS and value < 0:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.NEGATIVE_VALUE,
                    message=f"{metric.value} cannot be negative, got {value}.",
                    row=offset,
                    column=value_column,
                )
            )

        raw_timestamp = (row.get(timestamp_column) or "").strip()
        row_timezone = (
            (row.get(timezone_column) or "").strip() if timezone_column else ""
        ) or default_timezone

        timestamp_utc: datetime | None = None
        original_timezone: str | None = None
        if raw_timestamp:
            fold = 0
            if row_timezone:
                try:
                    zone = resolve_zone(row_timezone)
                    naive_candidate = datetime.fromisoformat(
                        raw_timestamp[:-1] + "+00:00"
                        if raw_timestamp.endswith(("Z", "z"))
                        else raw_timestamp
                    )
                    if naive_candidate.tzinfo is None:
                        kind = classify_local_time(naive_candidate, zone)
                        if kind == "ambiguous":
                            key = (row_timezone, naive_candidate)
                            occurrence = ambiguous_occurrences.get(key, 0)
                            if occurrence > 1:
                                issues.append(
                                    IngestionIssue(
                                        severity=IssueSeverity.ERROR,
                                        code=IssueCode.DUPLICATE_HOUR,
                                        message=(
                                            f"Local time {raw_timestamp!r} occurs more than "
                                            f"twice in {row_timezone}."
                                        ),
                                        row=offset,
                                        column=timestamp_column,
                                    )
                                )
                            fold = occurrence
                            ambiguous_occurrences[key] = occurrence + 1
                        elif kind == "nonexistent":
                            issues.append(
                                IngestionIssue(
                                    severity=IssueSeverity.ERROR,
                                    code=IssueCode.NONEXISTENT_TIMESTAMP,
                                    message=(
                                        f"Local time {raw_timestamp!r} was skipped by a "
                                        f"daylight-saving transition in {row_timezone}."
                                    ),
                                    row=offset,
                                    column=timestamp_column,
                                )
                            )
                except TimezoneResolutionError as exc:
                    issues.append(
                        IngestionIssue(
                            severity=IssueSeverity.ERROR,
                            code=IssueCode.MISSING_TIMEZONE,
                            message=str(exc),
                            row=offset,
                            column=timezone_column or timestamp_column,
                        )
                    )

            try:
                timestamp_utc, original_timezone = parse_timestamp(
                    raw_timestamp, timezone_name=row_timezone or None, fold=fold
                )
            except TimezoneResolutionError as exc:
                issues.append(
                    IngestionIssue(
                        severity=IssueSeverity.ERROR,
                        code=IssueCode.INVALID_TIMESTAMP,
                        message=str(exc),
                        row=offset,
                        column=timestamp_column,
                    )
                )
        else:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.INVALID_TIMESTAMP,
                    message="Timestamp is empty.",
                    row=offset,
                    column=timestamp_column,
                )
            )

        raw_location = (row.get(location_column) or "").strip() if location_column else ""
        location_id = raw_location or default_location_id

        if len(issues) != row_issues_before:
            continue

        assert metric is not None  # narrowed by the issue checks above
        assert unit is not None
        assert value is not None
        assert timestamp_utc is not None
        assert original_timezone is not None

        canonical_value, canonical_unit = _canonicalize(value, unit, metric)
        observations.append(
            Observation(
                timestamp_utc=timestamp_utc,
                location_id=location_id,
                metric=metric,
                value=canonical_value,
                unit=canonical_unit,
                source=source,
                data_status=data_status,
                original_timestamp=raw_timestamp,
                original_timezone=original_timezone,
                original_value=value,
                original_unit=unit,
                retrieved_at=retrieved_at or datetime.now(UTC),
            )
        )
        accepted += 1

    if not observations and not issues:
        issues.append(
            IngestionIssue(
                severity=IssueSeverity.ERROR,
                code=IssueCode.EMPTY_DATASET,
                message="No valid observations were found.",
            )
        )

    if issues and any(issue.severity is IssueSeverity.ERROR for issue in issues):
        raise DatasetValidationError(issues)

    grouped: dict[tuple[str, Metric], list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.location_id, observation.metric)].append(observation)

    series: dict[Metric, ObservationSeries] = {}
    for (location_id, metric), members in grouped.items():
        unique, contiguous, gaps = _dedupe_and_check_gaps(
            members, metric=metric, allow_gaps=allow_gaps, issues=issues
        )
        series[metric] = ObservationSeries(
            location_id=location_id,
            metric=metric,
            unit=members[0].unit,
            observations=tuple(unique),
            is_contiguous=contiguous,
            gaps=gaps,
        )

    for metric in CURRENCY_METRICS & series.keys():
        currencies = {observation.original_unit for observation in series[metric].observations}
        if len(currencies) > 1:
            issues.append(
                IngestionIssue(
                    severity=IssueSeverity.ERROR,
                    code=IssueCode.CURRENCY_MISMATCH,
                    message=(
                        f"{metric.value} mixes currencies "
                        f"({', '.join(sorted(unit.value for unit in currencies))}). "
                        "Convert to a single currency before uploading."
                    ),
                )
            )

    if any(issue.severity is IssueSeverity.ERROR for issue in issues):
        raise DatasetValidationError(issues)

    resolved_id = dataset_id or uuid4()
    resolved_retrieved_at = retrieved_at or datetime.now(UTC)
    checksum = _checksum(series, source=source, data_status=data_status)

    summaries = tuple(
        SeriesSummary(
            metric=metric,
            unit=current.unit,
            hours=current.hours,
            start_utc=current.start_utc,
            end_utc=current.end_utc,
            minimum=min(observation.value for observation in current.observations),
            maximum=current.peak,
            total=current.total,
            is_contiguous=current.is_contiguous,
        )
        for metric, current in sorted(series.items(), key=lambda item: item[0].value)
    )

    report = IngestionReport(
        dataset_id=resolved_id,
        source=source,
        data_status=data_status,
        retrieved_at=resolved_retrieved_at,
        checksum=checksum,
        rows_read=len(rows),
        rows_accepted=accepted,
        series=summaries,
        warnings=tuple(issue for issue in issues if issue.severity is IssueSeverity.WARNING),
    )

    return IngestedDataset(
        dataset_id=resolved_id,
        source=source,
        data_status=data_status,
        retrieved_at=resolved_retrieved_at,
        checksum=checksum,
        series=series,
        report=report,
    )


def ingest_csv_bytes(data: bytes, **kwargs: Any) -> IngestedDataset:
    """Decode an uploaded file (tolerating a UTF-8 BOM) and ingest it."""
    return ingest_csv(data.decode("utf-8-sig"), **kwargs)
