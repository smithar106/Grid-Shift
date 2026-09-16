"""Deletion semantics.

Deletes are the one place where a mistake is unrecoverable, so the rules are explicit:
a facility or dataset that still has dependents refuses to disappear, and the counts are
reported so the caller knows exactly what stands in the way.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import HourlyObservation
from app.models.facility import Facility
from app.models.scenario import HourlyAllocation, OptimizationResultRecord
from tests.conftest import create_facility, sample_dataset_csv, upload_dataset


def make_scenario(client: TestClient, facility_id: str, dataset_id: str, name: str = "S") -> dict:
    return client.post(
        "/api/v1/scenarios",
        json={
            "facility_id": facility_id,
            "name": name,
            "objective": "cost",
            "dataset_ids": [dataset_id],
            "workloads": [
                {
                    "job_id": "batch",
                    "energy_mwh": 120.0,
                    "release_hour": 0,
                    "deadline_hour": 23,
                    "max_mw": 20.0,
                }
            ],
        },
    ).json()


# --- Scenarios ----------------------------------------------------------------------


def test_delete_scenario_removes_it(client: TestClient) -> None:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    scenario = make_scenario(client, facility["id"], dataset["id"])

    assert client.delete(f"/api/v1/scenarios/{scenario['id']}").status_code == 204
    assert client.get(f"/api/v1/scenarios/{scenario['id']}").status_code == 404
    assert client.get("/api/v1/scenarios").json() == []


def test_delete_scenario_removes_results_and_allocations(
    client: TestClient, db_session: Session
) -> None:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    scenario = make_scenario(client, facility["id"], dataset["id"])
    client.post(f"/api/v1/scenarios/{scenario['id']}/optimize")

    assert db_session.scalar(select(OptimizationResultRecord)) is not None
    assert db_session.scalar(select(HourlyAllocation)) is not None

    assert client.delete(f"/api/v1/scenarios/{scenario['id']}").status_code == 204
    db_session.expire_all()

    assert db_session.scalars(select(OptimizationResultRecord)).all() == []
    assert db_session.scalars(select(HourlyAllocation)).all() == []


def test_delete_unknown_scenario_returns_404(client: TestClient) -> None:
    assert client.delete(f"/api/v1/scenarios/{uuid4()}").status_code == 404


def test_deleting_a_scenario_keeps_its_datasets(client: TestClient) -> None:
    """A scenario is derived; the evidence behind it is not."""
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    scenario = make_scenario(client, facility["id"], dataset["id"])

    client.delete(f"/api/v1/scenarios/{scenario['id']}")

    assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 200


# --- Datasets -----------------------------------------------------------------------


def test_delete_dataset_removes_its_observations(client: TestClient, db_session: Session) -> None:
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    assert db_session.scalars(select(HourlyObservation)).all() != []

    assert client.delete(f"/api/v1/datasets/{dataset['id']}").status_code == 204
    db_session.expire_all()

    assert db_session.scalars(select(HourlyObservation)).all() == []
    assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 404


def test_delete_dataset_referenced_by_a_scenario_is_refused(client: TestClient) -> None:
    """Deleting the evidence behind a saved result would break reproducibility."""
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    make_scenario(client, facility["id"], dataset["id"], name="Keeps evidence")

    response = client.delete(f"/api/v1/datasets/{dataset['id']}")

    assert response.status_code == 409
    assert "Keeps evidence" in response.json()["detail"]
    assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 200


def test_delete_dataset_referenced_by_a_scenario_can_be_forced(client: TestClient) -> None:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv())["body"]
    make_scenario(client, facility["id"], dataset["id"])

    assert client.delete(f"/api/v1/datasets/{dataset['id']}?force=true").status_code == 204
    assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 404


def test_delete_unknown_dataset_returns_404(client: TestClient) -> None:
    assert client.delete(f"/api/v1/datasets/{uuid4()}").status_code == 404


# --- Facilities ---------------------------------------------------------------------


def test_delete_facility_with_no_dependents(client: TestClient) -> None:
    facility = create_facility(client)
    assert client.delete(f"/api/v1/facilities/{facility['id']}").status_code == 204
    assert client.get(f"/api/v1/facilities/{facility['id']}").status_code == 404


def test_delete_facility_with_dependents_is_refused_with_counts(client: TestClient) -> None:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv(), facility_id=facility["id"])[
        "body"
    ]
    make_scenario(client, facility["id"], dataset["id"])

    response = client.delete(f"/api/v1/facilities/{facility['id']}")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "1 scenario(s)" in detail
    assert "1 dataset(s)" in detail
    assert "?force=true" in detail
    assert client.get(f"/api/v1/facilities/{facility['id']}").status_code == 200


def test_force_delete_facility_removes_scenarios_and_detaches_datasets(
    client: TestClient, db_session: Session
) -> None:
    facility = create_facility(client)
    dataset = upload_dataset(client, csv_text=sample_dataset_csv(), facility_id=facility["id"])[
        "body"
    ]
    make_scenario(client, facility["id"], dataset["id"])

    response = client.delete(f"/api/v1/facilities/{facility['id']}?force=true")

    assert response.status_code == 204
    assert client.get(f"/api/v1/facilities/{facility['id']}").status_code == 404
    assert client.get("/api/v1/scenarios").json() == []

    # The dataset survives, detached, with its observations intact.
    detached = client.get(f"/api/v1/datasets/{dataset['id']}").json()
    assert detached["facility_id"] is None
    db_session.expire_all()
    assert db_session.scalars(select(HourlyObservation)).all() != []


def test_delete_unknown_facility_returns_404(client: TestClient) -> None:
    assert client.delete(f"/api/v1/facilities/{uuid4()}").status_code == 404


def test_force_delete_does_not_touch_other_facilities(
    client: TestClient, db_session: Session
) -> None:
    keep = create_facility(client, location_id="facility_keep")
    drop = create_facility(client, location_id="facility_drop")
    dataset = upload_dataset(client, csv_text=sample_dataset_csv(), facility_id=drop["id"])["body"]
    make_scenario(client, drop["id"], dataset["id"])

    client.delete(f"/api/v1/facilities/{drop['id']}?force=true")
    db_session.expire_all()

    survivors = [f.location_id for f in db_session.scalars(select(Facility))]
    assert survivors == ["facility_keep"]
    assert client.get(f"/api/v1/facilities/{keep['id']}").status_code == 200
