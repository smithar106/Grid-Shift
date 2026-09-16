"""Load the synthetic sample facility into a running GridShift API.

This makes the repository's demonstration reproducible: anyone can clone GridShift, start
it, run this script, and get the same facility, dataset, and three objective scenarios that
the README screenshots show.

Usage::

    python scripts/seed_sample.py
    python scripts/seed_sample.py --api http://127.0.0.1:8000 --hours 24
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC = REPO_ROOT / "data" / "synthetic"

FACILITY = {
    "name": "Northern Virginia DC-1",
    "location_id": "facility_001",
    "latitude": 39.0438,
    "longitude": -77.4874,
    "timezone": "America/New_York",
    "capacity_mw": 38.0,
}

#: Hour index 0 is Monday 00:00 UTC in the generated sample.
HOURS_PER_DAY = 24
FORTNIGHT = 14 * HOURS_PER_DAY

#: A large training job with a fortnight to run in, and an inference batch with a week.
FLEXIBLE_WORKLOADS = [
    {
        "job_id": "model-training",
        "energy_mwh": 1200.0,
        "release_hour": 0,
        "deadline_hour": FORTNIGHT - 1,
        "max_mw": 30.0,
    },
    {
        "job_id": "batch-inference",
        "energy_mwh": 400.0,
        "release_hour": 0,
        "deadline_hour": FORTNIGHT - 1,
        "max_mw": 12.0,
    },
]

#: The same work, but the training job must finish inside the first three days. Comparing
#: this against the unconstrained runs is the point: flexibility has a price.
CONSTRAINED_WORKLOADS = [
    {**FLEXIBLE_WORKLOADS[0], "deadline_hour": 3 * HOURS_PER_DAY - 1},
    FLEXIBLE_WORKLOADS[1],
]

SCENARIOS = [
    ("Cost-optimized fortnight", "cost", 0.0, FLEXIBLE_WORKLOADS),
    ("Carbon-optimized fortnight", "emissions", 0.0, FLEXIBLE_WORKLOADS),
    ("Balanced at 80 USD per tonne", "balanced", 80.0, FLEXIBLE_WORKLOADS),
    ("Cost-optimized, 3-day deadline", "cost", 0.0, CONSTRAINED_WORKLOADS),
]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument(
        "--hours",
        type=int,
        default=336,
        choices=[24, 168, 336],
        help="Which generated sample to load (default: 336, i.e. 14 days).",
    )
    args = parser.parse_args()

    base = f"{args.api.rstrip('/')}/api/v1"
    sample = SYNTHETIC / f"sample_facility_{args.hours}h.csv"
    if not sample.exists():
        fail(
            f"{sample} is missing. Generate it first:\n"
            "  python scripts/generate_sample_data.py --hours 168"
        )

    with httpx.Client(timeout=60.0) as client:
        try:
            health = client.get(f"{base}/health")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            fail(f"GridShift API is not reachable at {args.api}: {exc}")

        print(f"api: {health.json()['service']} ({health.json()['environment']})")

        existing = client.get(f"{base}/facilities").json()
        facility = next(
            (item for item in existing if item["location_id"] == FACILITY["location_id"]),
            None,
        )
        if facility is None:
            response = client.post(f"{base}/facilities", json=FACILITY)
            if response.status_code != 201:
                fail(f"could not create facility: {response.text}")
            facility = response.json()
            print(f"facility: created {facility['name']} ({facility['id'][:8]})")
        else:
            print(f"facility: reusing {facility['name']} ({facility['id'][:8]})")

        with sample.open("rb") as handle:
            response = client.post(
                f"{base}/datasets",
                files={"file": (sample.name, handle, "text/csv")},
                data={"facility_id": facility["id"]},
            )
        if response.status_code != 201:
            fail(f"dataset upload rejected: {response.text}")
        dataset = response.json()
        print(
            f"dataset: {dataset['rows_accepted']} rows, "
            f"{len(dataset['metrics'])} metrics, checksum {dataset['checksum'][:10]}"
        )

        for name, objective, carbon_price, workloads in SCENARIOS:
            response = client.post(
                f"{base}/scenarios",
                json={
                    "facility_id": facility["id"],
                    "name": name,
                    "objective": objective,
                    "carbon_price_usd_per_tco2e": carbon_price,
                    "dataset_ids": [dataset["id"]],
                    "workloads": workloads,
                },
            )
            if response.status_code != 201:
                fail(f"could not create scenario {name!r}: {response.text}")
            scenario = response.json()

            result = client.post(f"{base}/scenarios/{scenario['id']}/optimize")
            if result.status_code != 200:
                fail(f"optimization failed for {name!r}: {result.text}")

            body = result.json()
            savings = body["cost_savings_pct"]
            reduction = body["emissions_reduction_pct"]
            print(
                f"  {name:32s} {body['status']:8s} "
                f"cost {body['total_cost_usd']:9,.0f} "
                f"({savings:+.2f}%)  emissions {body['total_emissions_tco2e']:7.2f} "
                f"({reduction:+.2f}%)"
            )

    print("\nSample data loaded. Open the dashboard to explore it.")


if __name__ == "__main__":
    main()
