"""Facility endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import create_facility


def test_create_facility_returns_the_created_record(client: TestClient) -> None:
    body = create_facility(client)

    assert body["location_id"] == "facility_001"
    assert body["capacity_mw"] == 40.0
    assert body["latitude"] == 37.7749
    assert body["id"]


def test_duplicate_location_id_is_rejected(client: TestClient) -> None:
    create_facility(client)
    response = client.post(
        "/api/v1/facilities",
        json={
            "name": "Another",
            "location_id": "facility_001",
            "timezone": "UTC",
            "capacity_mw": 10.0,
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_list_facilities(client: TestClient) -> None:
    create_facility(client, location_id="facility_a")
    create_facility(client, location_id="facility_b")

    response = client.get("/api/v1/facilities")
    assert response.status_code == 200
    assert {item["location_id"] for item in response.json()} == {"facility_a", "facility_b"}


def test_get_facility_by_id(client: TestClient) -> None:
    created = create_facility(client)
    response = client.get(f"/api/v1/facilities/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_facility_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/facilities/{uuid4()}")
    assert response.status_code == 404


def test_capacity_must_be_positive(client: TestClient) -> None:
    response = client.post(
        "/api/v1/facilities",
        json={
            "name": "Bad",
            "location_id": "facility_bad",
            "timezone": "UTC",
            "capacity_mw": 0,
        },
    )
    assert response.status_code == 422
