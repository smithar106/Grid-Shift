import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.enums import DataSource, DataStatus, Metric, Unit
from app.schemas.ingestion import DatasetValidationError, IssueCode, IssueSeverity
from app.services.csv_ingest import ingest_csv, ingest_csv_bytes

BASE = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def build_csv(rows: list[dict[str, str]], columns: list[str] | None = None) -> str:
    if not rows:
        return ",".join(columns or [])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def hourly_rows(
    metric: str,
    unit: str,
    values: list[float],
    *,
    start: datetime = BASE,
    location: str | None = None,
) -> list[dict[str, str]]:
    rows = []
    for index, value in enumerate(values):
        row = {
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "metric": metric,
            "value": str(value),
            "unit": unit,
        }
        if location is not None:
            row["location_id"] = location
        rows.append(row)
    return rows


def codes(error: DatasetValidationError) -> set[IssueCode]:
    return {issue.code for issue in error.issues}


# --- Happy path --------------------------------------------------------------------


def test_ingests_complete_hourly_price_series() -> None:
    values = [40.0 + index for index in range(24)]
    dataset = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", values)))

    series = dataset.series[Metric.ELECTRICITY_PRICE]
    assert series.hours == 24
    assert series.is_contiguous is True
    assert series.unit is Unit.USD_PER_MWH
    assert series.dense_values() == values
    assert dataset.report.rows_read == 24
    assert dataset.report.rows_accepted == 24
    assert dataset.report.warnings == ()
    assert dataset.data_status is DataStatus.USER_SUPPLIED
    assert dataset.source is DataSource.UPLOADED_CSV


def test_normalizes_timestamps_to_utc_and_keeps_original_zone() -> None:
    rows = [
        {
            "timestamp": "2026-09-16T00:00:00-07:00",
            "metric": "electricity_price",
            "value": "50",
            "unit": "USD/MWh",
        }
    ]
    dataset = ingest_csv(build_csv(rows))
    observation = dataset.series[Metric.ELECTRICITY_PRICE].observations[0]

    assert observation.timestamp_utc == datetime(2026, 9, 16, 7, 0, tzinfo=UTC)
    assert observation.original_timezone == "-07:00"
    assert observation.original_timestamp == "2026-09-16T00:00:00-07:00"


def test_localizes_naive_timestamps_using_timezone_column() -> None:
    rows = [
        {
            "timestamp": "2026-09-16T00:00:00",
            "metric": "electricity_price",
            "value": "50",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        }
    ]
    dataset = ingest_csv(build_csv(rows))
    observation = dataset.series[Metric.ELECTRICITY_PRICE].observations[0]
    assert observation.timestamp_utc == datetime(2026, 9, 16, 7, 0, tzinfo=UTC)
    assert observation.original_timezone == "America/Los_Angeles"


def test_default_timezone_argument_applies_to_naive_timestamps() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [1.0] * 24)
    for row in rows:
        row["timestamp"] = row["timestamp"].replace("+00:00", "")
    dataset = ingest_csv(build_csv(rows), default_timezone="Europe/London")
    assert dataset.series[Metric.ELECTRICITY_PRICE].observations[0].original_timezone == (
        "Europe/London"
    )


def test_accepts_multiple_metrics_in_one_file() -> None:
    rows = [
        *hourly_rows("electricity_price", "USD/MWh", [10.0] * 24),
        *hourly_rows("carbon_intensity", "tCO2e/MWh", [0.4] * 24),
        *hourly_rows("facility_load", "MWh", [5.0] * 24),
    ]
    dataset = ingest_csv(build_csv(rows))
    assert set(dataset.series) == {
        Metric.ELECTRICITY_PRICE,
        Metric.CARBON_INTENSITY,
        Metric.FACILITY_LOAD,
    }
    assert len(dataset.report.series) == 3


def test_metric_and_unit_aliases_are_accepted() -> None:
    rows = [
        {"timestamp": BASE.isoformat(), "metric": "price", "value": "10", "unit": "$/MWh"},
        {
            "timestamp": (BASE + timedelta(hours=1)).isoformat(),
            "metric": "price",
            "value": "11",
            "unit": "$/MWh",
        },
    ]
    dataset = ingest_csv(build_csv(rows))
    assert dataset.series[Metric.ELECTRICITY_PRICE].unit is Unit.USD_PER_MWH


# --- Unit canonicalization ---------------------------------------------------------


def test_converts_kilograms_to_tonnes_of_co2e() -> None:
    dataset = ingest_csv(build_csv(hourly_rows("carbon_intensity", "kgCO2e/MWh", [500.0] * 24)))
    observation = dataset.series[Metric.CARBON_INTENSITY].observations[0]

    assert observation.value == pytest.approx(0.5)
    assert observation.unit is Unit.TONNES_CO2E_PER_MWH
    assert observation.original_value == 500.0
    assert observation.original_unit is Unit.KG_CO2E_PER_MWH


def test_converts_kilowatt_hours_to_megawatt_hours() -> None:
    dataset = ingest_csv(build_csv(hourly_rows("facility_load", "kWh", [2500.0] * 24)))
    observation = dataset.series[Metric.FACILITY_LOAD].observations[0]

    assert observation.value == pytest.approx(2.5)
    assert observation.unit is Unit.MWH
    assert observation.original_unit is Unit.KWH


# --- Value validation --------------------------------------------------------------


def test_negative_electricity_prices_are_allowed() -> None:
    values = [-30.0, -5.0, 0.0, 12.0]
    dataset = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", values)))
    assert dataset.series[Metric.ELECTRICITY_PRICE].dense_values() == values


def test_zero_price_hours_are_preserved() -> None:
    values = [0.0] * 24
    dataset = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", values)))
    assert dataset.series[Metric.ELECTRICITY_PRICE].total == 0.0


def test_negative_facility_load_is_rejected() -> None:
    rows = hourly_rows("facility_load", "MWh", [5.0] * 24)
    rows[3]["value"] = "-1"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.NEGATIVE_VALUE in codes(error.value)


def test_negative_carbon_intensity_is_rejected() -> None:
    rows = hourly_rows("carbon_intensity", "tCO2e/MWh", [0.4] * 24)
    rows[0]["value"] = "-0.1"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.NEGATIVE_VALUE in codes(error.value)


@pytest.mark.parametrize("bad_value", ["", "abc", "NaN", "inf", "1,5"])
def test_non_numeric_values_are_rejected(bad_value: str) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows[2]["value"] = bad_value

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.INVALID_VALUE in codes(error.value)


# --- Schema validation -------------------------------------------------------------


def test_unknown_metric_is_rejected() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows[0]["metric"] = "vibes"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.UNKNOWN_METRIC in codes(error.value)


def test_unknown_unit_is_rejected() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows[0]["unit"] = "bananas/MWh"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.UNKNOWN_UNIT in codes(error.value)


def test_incompatible_unit_is_rejected() -> None:
    rows = hourly_rows("electricity_price", "MWh", [10.0] * 24)

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.INCOMPATIBLE_UNIT in codes(error.value)


def test_missing_required_column_is_reported() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    for row in rows:
        del row["unit"]

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.MISSING_COLUMN in codes(error.value)


def test_naive_timestamp_without_timezone_is_rejected() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    for row in rows:
        row["timestamp"] = row["timestamp"].replace("+00:00", "")

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.INVALID_TIMESTAMP in codes(error.value)


def test_empty_file_is_rejected() -> None:
    with pytest.raises(DatasetValidationError) as error:
        ingest_csv("")
    assert IssueCode.EMPTY_DATASET in codes(error.value)


def test_header_only_file_is_rejected() -> None:
    with pytest.raises(DatasetValidationError) as error:
        ingest_csv("timestamp,metric,value,unit\n")
    assert IssueCode.EMPTY_DATASET in codes(error.value)


def test_row_limit_is_enforced() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [1.0] * 10)
    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows), max_rows=5)
    assert IssueCode.ROW_LIMIT_EXCEEDED in codes(error.value)


# --- Hourly coverage ---------------------------------------------------------------


def test_duplicate_hour_is_rejected() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows.append(dict(rows[0]))

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.DUPLICATE_HOUR in codes(error.value)


def test_missing_hour_is_rejected_by_default() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    del rows[5]

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.MISSING_HOUR in codes(error.value)


def test_missing_hour_is_accepted_when_explicitly_allowed() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    del rows[5]

    dataset = ingest_csv(build_csv(rows), allow_gaps=True)
    series = dataset.series[Metric.ELECTRICITY_PRICE]

    assert series.hours == 23
    assert series.is_contiguous is False
    assert len(series.gaps) == 1
    assert dataset.report.warnings[0].code is IssueCode.MISSING_HOUR
    assert dataset.report.warnings[0].severity is IssueSeverity.WARNING

    with pytest.raises(ValueError, match="cannot be densified"):
        series.dense_values()


def test_unsorted_rows_are_sorted_into_a_contiguous_series() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [float(index) for index in range(24)])
    shuffled = [rows[index] for index in (5, 0, 23, 11)] + [
        rows[index] for index in range(1, 23) if index not in (5, 11)
    ]

    dataset = ingest_csv(build_csv(shuffled))
    assert dataset.series[Metric.ELECTRICITY_PRICE].dense_values() == [
        float(index) for index in range(24)
    ]


# --- Currency consistency ----------------------------------------------------------


def test_mixed_currencies_in_one_price_series_are_rejected() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows[10]["unit"] = "EUR/MWh"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.CURRENCY_MISMATCH in codes(error.value)


# --- Daylight saving ---------------------------------------------------------------


def test_fall_back_repeated_hour_produces_two_distinct_utc_instants() -> None:
    """A 25-hour day must survive as 25 hours, not be rejected as a duplicate."""
    rows = [
        {
            "timestamp": "2026-11-01T00:00:00",
            "metric": "electricity_price",
            "value": "10",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        },
        {
            "timestamp": "2026-11-01T01:00:00",
            "metric": "electricity_price",
            "value": "20",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        },
        {
            "timestamp": "2026-11-01T01:00:00",
            "metric": "electricity_price",
            "value": "30",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        },
        {
            "timestamp": "2026-11-01T02:00:00",
            "metric": "electricity_price",
            "value": "40",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        },
    ]
    dataset = ingest_csv(build_csv(rows))
    series = dataset.series[Metric.ELECTRICITY_PRICE]

    assert series.hours == 4
    assert series.is_contiguous is True
    assert [observation.timestamp_utc.hour for observation in series.observations] == [7, 8, 9, 10]
    assert series.dense_values() == [10.0, 20.0, 30.0, 40.0]


def test_spring_forward_nonexistent_hour_is_rejected() -> None:
    rows = [
        {
            "timestamp": f"2026-03-08T{hour:02d}:00:00",
            "metric": "electricity_price",
            "value": "10",
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        }
        for hour in (1, 2, 3)
    ]

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.NONEXISTENT_TIMESTAMP in codes(error.value)


def test_fall_back_hour_repeated_three_times_is_rejected() -> None:
    rows = [
        {
            "timestamp": "2026-11-01T01:30:00",
            "metric": "electricity_price",
            "value": str(index),
            "unit": "USD/MWh",
            "timezone": "America/Los_Angeles",
        }
        for index in range(3)
    ]

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))
    assert IssueCode.DUPLICATE_HOUR in codes(error.value)


# --- Provenance and reproducibility ------------------------------------------------


def test_identical_input_produces_identical_checksum() -> None:
    payload = build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24))
    first = ingest_csv(payload)
    second = ingest_csv(payload)
    assert first.checksum == second.checksum


def test_different_values_produce_different_checksums() -> None:
    first = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)))
    second = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", [11.0] * 24)))
    assert first.checksum != second.checksum


def test_checksum_ignores_row_order() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [float(index) for index in range(24)])
    forward = ingest_csv(build_csv(rows))
    reversed_rows = list(reversed(rows))
    backward = ingest_csv(build_csv(reversed_rows))
    assert forward.checksum == backward.checksum


def test_source_and_status_flow_through_to_observations() -> None:
    dataset = ingest_csv(
        build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)),
        source=DataSource.SYNTHETIC_SAMPLE,
        data_status=DataStatus.SYNTHETIC,
    )
    observation = dataset.series[Metric.ELECTRICITY_PRICE].observations[0]
    assert observation.source is DataSource.SYNTHETIC_SAMPLE
    assert observation.data_status is DataStatus.SYNTHETIC


def test_retrieved_at_is_recorded() -> None:
    moment = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    dataset = ingest_csv(
        build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)),
        retrieved_at=moment,
    )
    assert dataset.report.retrieved_at == moment
    assert dataset.series[Metric.ELECTRICITY_PRICE].observations[0].retrieved_at == moment


# --- Location handling -------------------------------------------------------------


def test_location_column_overrides_default() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24, location="facility_007")
    dataset = ingest_csv(build_csv(rows), default_location_id="facility_001")
    assert dataset.series[Metric.ELECTRICITY_PRICE].location_id == "facility_007"


def test_default_location_used_when_column_absent() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    dataset = ingest_csv(build_csv(rows), default_location_id="facility_042")
    assert dataset.series[Metric.ELECTRICITY_PRICE].location_id == "facility_042"


# --- require() ---------------------------------------------------------------------


def test_require_raises_with_available_metrics_listed() -> None:
    dataset = ingest_csv(build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)))
    with pytest.raises(DatasetValidationError, match="electricity_price"):
        dataset.require(Metric.CARBON_INTENSITY)


def test_require_returns_requested_series() -> None:
    dataset = ingest_csv(build_csv(hourly_rows("facility_load", "MWh", [3.0] * 24)))
    assert dataset.require(Metric.FACILITY_LOAD).hours == 24


# --- Upload handling ---------------------------------------------------------------


def test_utf8_bom_is_tolerated() -> None:
    payload = build_csv(hourly_rows("electricity_price", "USD/MWh", [10.0] * 24))
    dataset = ingest_csv_bytes(b"\xef\xbb\xbf" + payload.encode())
    assert dataset.series[Metric.ELECTRICITY_PRICE].hours == 24


def test_report_summarizes_each_series() -> None:
    rows = [
        *hourly_rows("electricity_price", "USD/MWh", [10.0] * 24),
        *hourly_rows("facility_load", "MWh", [4.0] * 24),
    ]
    report = ingest_csv(build_csv(rows)).report
    summary = {item.metric: item for item in report.series}

    assert summary[Metric.ELECTRICITY_PRICE].minimum == 10.0
    assert summary[Metric.ELECTRICITY_PRICE].maximum == 10.0
    assert summary[Metric.ELECTRICITY_PRICE].total == 240.0
    assert summary[Metric.FACILITY_LOAD].hours == 24
    assert all(item.is_contiguous for item in report.series)


def test_many_errors_are_reported_together() -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows[0]["metric"] = "nonsense"
    rows[1]["unit"] = "bananas"
    rows[2]["value"] = "not-a-number"

    with pytest.raises(DatasetValidationError) as error:
        ingest_csv(build_csv(rows))

    assert codes(error.value) >= {
        IssueCode.UNKNOWN_METRIC,
        IssueCode.UNKNOWN_UNIT,
        IssueCode.INVALID_VALUE,
    }
    assert len(error.value.issues) >= 3
