"""Generate the synthetic sample facility dataset.

GridShift does not have access to proprietary data-center telemetry, so the shipped
sample is synthetic. It is generated deterministically — a fixed start date and a
hash-based pseudo-random, never a seeded RNG — which means the published CSV is stable and
the repository's example results can be checked by anyone.

The default horizon is two weeks at hourly resolution (336 hours x 3 metrics = 1008 rows).
A fortnight is long enough that day-of-week effects and day-to-day volatility are real,
which is what makes cross-day shifting a genuine decision rather than a toy one.

The profile is deliberately shaped so the earliest-feasible baseline is *not* already
optimal: prices and carbon intensity peak in the morning ramp and again in the evening,
while the earliest-feasible scheduler front-loads work into the morning peak. A flat curve
would make every objective agree and hide whether the comparison works at all.

Every value produced here is labelled ``synthetic_sample`` and ``synthetic`` in the
ingestion pipeline. Synthetic data is never substituted for a failed live retrieval.

Usage::

    python scripts/generate_sample_data.py                  # 336 hours (14 days)
    python scripts/generate_sample_data.py --hours 168      # one week
    python scripts/generate_sample_data.py --hours 24       # a single day
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

#: The sample horizon starts on a Monday so day-of-week patterns line up.
START = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)

#: Facility parameters for the synthetic site.
CAPACITY_MW = 38.0
LOCATION_ID = "facility_001"

DEFAULT_HOURS = 336

COLUMNS = ("timestamp", "location_id", "metric", "value", "unit")


def _noise(index: int, salt: str) -> float:
    """Deterministic pseudo-random value in [-1, 1].

    A hash rather than an RNG so the generated file never changes between runs or
    machines. Reproducibility is a product requirement, and it starts with the fixtures.
    """
    digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
    return (int.from_bytes(digest[:4], "big") / 0xFFFFFFFF) * 2.0 - 1.0


def _gaussian(value: float, centre: float, width: float) -> float:
    return math.exp(-((value - centre) ** 2) / width)


def _day_parts(hour: int) -> tuple[int, int, int, bool]:
    """Return (day index, hour of day, day of week, is weekend)."""
    day, hour_of_day = divmod(hour, 24)
    day_of_week = day % 7  # 0 = Monday
    return day, hour_of_day, day_of_week, day_of_week >= 5


def electricity_price(hour: int) -> float:
    """USD/MWh. Overnight baseload, a morning ramp, an evening peak, and volatility."""
    day, hour_of_day, _, weekend = _day_parts(hour)

    base = 24.0 if weekend else 29.0
    morning = (34.0 if weekend else 44.0) * _gaussian(hour_of_day, 8.0, 7.0)
    evening = (40.0 if weekend else 54.0) * _gaussian(hour_of_day, 18.0, 6.0)

    # Day-level drift plus occasional scarcity spikes.
    drift = 7.0 * _noise(day, "price-drift")
    spike = 22.0 * _noise(hour, "price-spike") if _noise(hour, "spike-flag") > 0.88 else 0.0
    jitter = 1.8 * _noise(hour, "price-jitter")

    return round(max(2.0, base + morning + evening + drift + spike + jitter), 2)


def carbon_intensity(hour: int) -> float:
    """tCO2e/MWh. Dirty when demand peaks and gas sets the marginal price.

    Midday is cleaner on weekdays, when solar output is highest and the facility is
    busiest — which is exactly the kind of misalignment between price and carbon that
    makes the three objectives disagree.
    """
    _, hour_of_day, _, weekend = _day_parts(hour)

    base = 0.215 if weekend else 0.235
    morning = (0.20 if weekend else 0.26) * _gaussian(hour_of_day, 8.5, 9.0)
    evening = (0.24 if weekend else 0.31) * _gaussian(hour_of_day, 18.5, 7.0)
    solar = -(0.09 if not weekend else 0.05) * _gaussian(hour_of_day, 12.5, 14.0)

    jitter = 0.012 * _noise(hour, "carbon-jitter")
    return round(max(0.05, base + morning + evening + solar + jitter), 4)


def facility_load(hour: int) -> float:
    """MWh. The fixed, non-shiftable load: cooling, networking, always-on services.

    Weekdays run hotter than weekends, and cooling tracks the afternoon.
    """
    _, hour_of_day, _, weekend = _day_parts(hour)

    base = 13.0 if weekend else 16.5
    cooling = 2.6 * _gaussian(hour_of_day, 15.0, 30.0)
    jitter = 0.35 * _noise(hour, "load-jitter")

    return round(max(1.0, base + cooling + jitter), 2)


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


def write(path: Path, hours: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = rows(hours)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(payload)
    return len(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help=f"Horizon length in hours (default: {DEFAULT_HOURS}, i.e. 14 days).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "synthetic",
        help="Directory to write into.",
    )
    args = parser.parse_args()

    if args.hours % 24 != 0:
        parser.error("--hours must be a whole number of days so the profile stays aligned.")

    path = args.output / f"sample_facility_{args.hours}h.csv"
    written = write(path, args.hours)

    prices = [electricity_price(h) for h in range(args.hours)]
    carbons = [carbon_intensity(h) for h in range(args.hours)]
    loads = [facility_load(h) for h in range(args.hours)]

    print(f"wrote {path}")
    print(f"  {args.hours} hours ({args.hours // 24} days) x 3 metrics = {written} rows")
    print(f"  price   {min(prices):.2f} - {max(prices):.2f} USD/MWh")
    print(f"  carbon  {min(carbons):.4f} - {max(carbons):.4f} tCO2e/MWh")
    print(f"  load    {min(loads):.2f} - {max(loads):.2f} MWh")


if __name__ == "__main__":
    main()
