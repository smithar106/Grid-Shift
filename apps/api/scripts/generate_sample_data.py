"""Generate the synthetic sample facility dataset.

GridShift does not have access to proprietary data-center telemetry, so the shipped
sample is synthetic. It is generated from a fixed seed, which means the published CSV is
reproducible and the repository's example results can be checked by anyone.

The profile is deliberately shaped so the earliest-feasible baseline is *not* already
optimal: prices and carbon intensity peak in the morning ramp and again in the evening,
while the earliest-feasible scheduler front-loads work into the morning peak. A flat curve
would make every objective agree and hide whether the comparison works at all.

Every value produced here is labelled ``synthetic_sample`` and ``synthetic`` in the
ingestion pipeline. Synthetic data is never substituted for a failed live retrieval.

Usage::

    python scripts/generate_sample_data.py                 # writes data/synthetic/
    python scripts/generate_sample_data.py --hours 168     # a week
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

#: The sample horizon starts here. Fixed so the published CSV never changes.
START = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)

#: Facility parameters for the synthetic site.
CAPACITY_MW = 38.0
LOCATION_ID = "facility_001"

COLUMNS = ("timestamp", "location_id", "metric", "value", "unit")


def _gaussian(hour: float, centre: float, width: float) -> float:
    return math.exp(-((hour - centre) ** 2) / width)


def electricity_price(hour: int) -> float:
    """USD/MWh. Overnight baseload, a morning ramp, and a sharper evening peak."""
    of_day = hour % 24
    return round(
        28.0 + 58.0 * _gaussian(of_day, 8.0, 7.0) + 64.0 * _gaussian(of_day, 18.0, 6.0),
        2,
    )


def carbon_intensity(hour: int) -> float:
    """tCO2e/MWh. Dirty when demand peaks and gas sets the marginal price."""
    of_day = hour % 24
    return round(
        0.20 + 0.30 * _gaussian(of_day, 8.5, 9.0) + 0.36 * _gaussian(of_day, 18.5, 7.0),
        4,
    )


def facility_load(hour: int) -> float:
    """MWh. The fixed, non-shiftable load: cooling, networking, always-on services."""
    return round(14.0 + 3.0 * math.sin(hour / 24.0 * 2 * math.pi), 2)


def rows(hours: int) -> list[dict[str, str]]:
    generated: list[dict[str, str]] = []
    for hour in range(hours):
        timestamp = (START + timedelta(hours=hour)).isoformat().replace("+00:00", "Z")
        for metric, value, unit in (
            ("electricity_price", electricity_price(hour), "USD/MWh"),
            ("carbon_intensity", carbon_intensity(hour), "tCO2e/MWh"),
            ("facility_load", facility_load(hour), "MWh"),
        ):
            generated.append(
                {
                    "timestamp": timestamp,
                    "location_id": LOCATION_ID,
                    "metric": metric,
                    "value": f"{value}",
                    "unit": unit,
                }
            )
    return generated


def write(path: Path, hours: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows(hours))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours", type=int, default=24, help="Horizon length in hours (default: 24)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "synthetic",
        help="Directory to write into.",
    )
    args = parser.parse_args()

    day = args.output / "sample_facility_24h.csv"
    week = args.output / "sample_facility_168h.csv"

    write(day, 24)
    print(f"wrote {day} (24 hours, 3 metrics, {24 * 3} rows)")

    if args.hours != 24:
        write(week, args.hours)
        print(f"wrote {week} ({args.hours} hours, 3 metrics, {args.hours * 3} rows)")


if __name__ == "__main__":
    main()
