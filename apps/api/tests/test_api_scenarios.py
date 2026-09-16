"""The end-to-end scenario flow: create, optimize, inspect, export.

This is the workflow the PRD calls the defining portfolio demonstration: load a facility,
upload hourly energy inputs, run all three objective modes, and compare against a feasible
baseline with full provenance.
"""

from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    build_csv,
    create_facility,
    hourly_rows,
    sample_dataset_csv,
    upload_dataset,
)


def setup_scenario(
    client: TestClient,
    *,
    objective: str = "cost",
    carbon_price: float = 0.0,
    workloads: list[dict] | None = None,
) -> dict:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]

    response = client.post(
        "/api/v1/scenarios",
        json={
            "facility_id": facility["id"],
            "name": "Baseline shift",
            "objective": objective,
            "carbon_price_usd_per_tco2e": carbon_price,
            "dataset_ids": [dataset["id"]],
            "workloads": (
                workloads
                if workloads is not None
                else [
                    {
                        "job_id": "batch-1",
                        "energy_mwh": 120.0,
                        "release_hour": 0,
                        "deadline_hour": 23,
                        "max_mw": 20.0,
                    }
                ]
            ),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_scenario(client: TestClient) -> None:
    scenario = setup_scenario(client)

    assert scenario["objective"] == "cost"
    assert scenario["status"] == "draft"
    assert len(scenario["workloads"]) == 1
    assert scenario["workloads"][0]["job_id"] == "batch-1"


def test_duplicate_job_ids_are_rejected(client: TestClient) -> None:
    facility = create_facility(client)
    workload = {
        "job_id": "same",
        "energy_mwh": 10.0,
        "release_hour": 0,
        "deadline_hour": 5,
        "max_mw": 5.0,
    }
    response = client.post(
        "/api/v1/scenarios",
        json={
            "facility_id": facility["id"],
            "name": "Dupes",
            "objective": "cost",
            "dataset_ids": [],
            "workloads": [workload, dict(workload)],
        },
    )

    assert response.status_code == 422
    assert "unique" in response.json()["detail"]


def test_scenario_with_unknown_facility_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/scenarios",
        json={"facility_id": str(uuid4()), "name": "Ghost", "objective": "cost"},
    )
    assert response.status_code == 404


def test_scenario_with_unknown_dataset_is_rejected(client: TestClient) -> None:
    facility = create_facility(client)
    response = client.post(
        "/api/v1/scenarios",
        json={
            "facility_id": facility["id"],
            "name": "Ghost data",
            "objective": "cost",
            "dataset_ids": [str(uuid4())],
        },
    )
    assert response.status_code == 404


def test_optimize_without_datasets_explains_what_is_missing(client: TestClient) -> None:
    facility = create_facility(client)
    created = client.post(
        "/api/v1/scenarios",
        json={"facility_id": facility["id"], "name": "Empty", "objective": "cost"},
    ).json()

    response = client.post(f"/api/v1/scenarios/{created['id']}/optimize")

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_scenario"
    assert "no datasets" in body["message"].lower()


def test_optimize_requires_prices_and_carbon(client: TestClient) -> None:
    facility = create_facility(client)
    only_prices = build_csv(hourly_rows("electricity_price", "USD/MWh", [50.0] * 24))
    dataset = upload_dataset(client, csv_text=only_prices)["body"]

    created = client.post(
        "/api/v1/scenarios",
        json={
            "facility_id": facility["id"],
            "name": "Incomplete",
            "objective": "cost",
            "dataset_ids": [dataset["id"]],
        },
    ).json()

    response = client.post(f"/api/v1/scenarios/{created['id']}/optimize")

    assert response.status_code == 422
    assert "carbon_intensity" in response.json()["message"]


def test_cost_optimization_end_to_end(client: TestClient) -> None:
    scenario = setup_scenario(client, objective="cost")
    response = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize")

    assert response.status_code == 200, response.text
    result = response.json()

    assert result["status"] == "optimal"
    assert result["objective_mode"] == "cost"
    assert len(result["hourly"]) == 24
    assert result["constraint_violations"] == []

    # The baseline front-loads expensive hours; the optimizer moves work later.
    assert result["total_cost_usd"] < result["baseline_total_cost_usd"]
    assert result["cost_savings_pct"] > 0
    assert result["emissions_reduction_pct"] is not None

    flexible = [point["optimized_flexible_mwh"] for point in result["hourly"]]
    assert sum(flexible[:12]) == pytest.approx(0.0, abs=1e-6)
    assert sum(flexible[12:]) == pytest.approx(120.0)


@pytest.mark.parametrize("objective", ["cost", "emissions", "balanced"])
def test_all_three_modes_run_and_report_both_quantities(client: TestClient, objective: str) -> None:
    scenario = setup_scenario(client, objective=objective, carbon_price=40.0)
    response = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize")

    assert response.status_code == 200, response.text
    result = response.json()

    assert result["status"] == "optimal"
    assert result["total_cost_usd"] > 0
    assert result["total_emissions_tco2e"] > 0
    assert result["baseline_total_cost_usd"] is not None
    assert result["baseline_total_emissions_tco2e"] is not None


def test_balanced_mode_prices_carbon_in_the_objective(client: TestClient) -> None:
    scenario = setup_scenario(client, objective="balanced", carbon_price=100.0)
    result = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    expected = result["total_cost_usd"] + 100.0 * result["total_emissions_tco2e"]
    assert result["objective_value"] == pytest.approx(expected, rel=1e-6)


def test_optimization_is_reproducible(client: TestClient) -> None:
    """Identical snapshots must produce equivalent results."""
    scenario = setup_scenario(client, objective="cost")
    first = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()
    second = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    assert first["total_cost_usd"] == pytest.approx(second["total_cost_usd"])
    assert first["job_allocations"] == second["job_allocations"]


def test_infeasible_scenario_returns_infeasible_status(client: TestClient) -> None:
    scenario = setup_scenario(
        client,
        objective="cost",
        workloads=[
            {
                "job_id": "impossible",
                "energy_mwh": 500.0,
                "release_hour": 3,
                "deadline_hour": 3,
                "max_mw": 10.0,
            }
        ],
    )
    result = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    assert result["status"] == "infeasible"
    assert "impossible" in result["diagnostics"]["message"]


def test_scenario_status_and_snapshot_are_recorded(client: TestClient) -> None:
    scenario = setup_scenario(client)
    client.post(f"/api/v1/scenarios/{scenario['id']}/optimize")

    refreshed = client.get(f"/api/v1/scenarios/{scenario['id']}").json()
    assert refreshed["status"] == "optimized"
    assert refreshed["snapshot_checksum"]


def test_results_endpoint_returns_the_latest_solve(client: TestClient) -> None:
    scenario = setup_scenario(client)
    optimized = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    fetched = client.get(f"/api/v1/scenarios/{scenario['id']}/results")
    assert fetched.status_code == 200
    assert fetched.json()["total_cost_usd"] == pytest.approx(optimized["total_cost_usd"])
    assert fetched.json()["job_allocations"] == optimized["job_allocations"]


def test_results_before_optimizing_returns_404_with_guidance(client: TestClient) -> None:
    scenario = setup_scenario(client)
    response = client.get(f"/api/v1/scenarios/{scenario['id']}/results")

    assert response.status_code == 404
    assert "optimize" in response.json()["detail"]


def test_optimize_unknown_scenario_returns_404(client: TestClient) -> None:
    assert client.post(f"/api/v1/scenarios/{uuid4()}/optimize").status_code == 404


def test_export_json_is_a_complete_result(client: TestClient) -> None:
    scenario = setup_scenario(client)
    optimized = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    response = client.get(f"/api/v1/scenarios/{scenario['id']}/export?format=json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    exported = response.json()
    assert exported["total_cost_usd"] == pytest.approx(optimized["total_cost_usd"])
    assert len(exported["hourly"]) == 24


def test_export_csv_has_a_row_per_hour(client: TestClient) -> None:
    scenario = setup_scenario(client)
    client.post(f"/api/v1/scenarios/{scenario['id']}/optimize")

    response = client.get(f"/api/v1/scenarios/{scenario['id']}/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 24
    assert rows[0]["timestamp_utc"].startswith("2026-09-16T00:00:00")
    assert float(rows[0]["price_usd_per_mwh"]) == 90.0


def test_export_rejects_unknown_format(client: TestClient) -> None:
    scenario = setup_scenario(client)
    assert client.get(f"/api/v1/scenarios/{scenario['id']}/export?format=xlsx").status_code == 422


def test_zero_workload_scenario_returns_the_fixed_load(client: TestClient) -> None:
    scenario = setup_scenario(client, workloads=[])
    result = client.post(f"/api/v1/scenarios/{scenario['id']}/optimize").json()

    assert result["status"] == "optimal"
    assert result["job_allocations"] == {}
    assert all(point["optimized_flexible_mwh"] == 0.0 for point in result["hourly"])
    assert result["cost_savings_pct"] == pytest.approx(0.0)


# --- Carbon-price trade-off sweep ---------------------------------------------------


def test_explore_returns_a_tradeoff_curve(client: TestClient) -> None:
    """Each point is a full solve, so the curve is the model's own frontier."""
    scenario = setup_scenario(client, objective="balanced")
    response = client.post(
        f"/api/v1/scenarios/{scenario['id']}/explore",
        json={"carbon_prices_usd_per_tco2e": [0.0, 50.0, 200.0]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [point["carbon_price_usd_per_tco2e"] for point in body["points"]] == [0.0, 50.0, 200.0]
    assert all(point["status"] == "optimal" for point in body["points"])
    assert body["baseline_total_cost_usd"] is not None
    assert body["horizon_hours"] == 24


def test_explore_higher_carbon_price_never_emits_more(client: TestClient) -> None:
    """Pricing carbon more highly cannot make the emissions-optimal choice worse."""
    scenario = setup_scenario(client, objective="balanced")
    body = client.post(
        f"/api/v1/scenarios/{scenario['id']}/explore",
        json={"carbon_prices_usd_per_tco2e": [0.0, 50.0, 500.0]},
    ).json()

    emissions = [point["total_emissions_tco2e"] for point in body["points"]]
    assert emissions == sorted(emissions, reverse=True)


def test_explore_uses_default_carbon_prices(client: TestClient) -> None:
    scenario = setup_scenario(client, objective="balanced")
    body = client.post(f"/api/v1/scenarios/{scenario['id']}/explore").json()
    assert len(body["points"]) >= 2


def test_explore_rejects_negative_carbon_prices(client: TestClient) -> None:
    scenario = setup_scenario(client, objective="balanced")
    response = client.post(
        f"/api/v1/scenarios/{scenario['id']}/explore",
        json={"carbon_prices_usd_per_tco2e": [-10.0, 20.0]},
    )
    assert response.status_code == 422


def test_explore_does_not_persist_a_result(client: TestClient) -> None:
    """A sweep is exploration; it must not pollute the scenario's result history."""
    scenario = setup_scenario(client, objective="balanced")
    client.post(f"/api/v1/scenarios/{scenario['id']}/explore")

    assert client.get(f"/api/v1/scenarios/{scenario['id']}/results").status_code == 404
