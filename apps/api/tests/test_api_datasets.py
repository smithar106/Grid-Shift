"""Dataset upload endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import (
    build_csv,
    create_facility,
    hourly_rows,
    sample_dataset_csv,
    upload_dataset,
)


def test_upload_valid_dataset(client: TestClient) -> None:
    result = upload_dataset(client, csv_text=sample_dataset_csv())
    assert result["status_code"] == 201, result["body"]

    body = result["body"]
    assert body["source"] == "uploaded_csv"
    assert body["data_status"] == "user_supplied"
    assert set(body["metrics"]) == {"electricity_price", "carbon_intensity", "facility_load"}
    assert body["rows_read"] == 72
    assert body["rows_accepted"] == 72
    assert len(body["checksum"]) == 64
    assert {item["metric"] for item in body["series"]} == {
        "electricity_price",
        "carbon_intensity",
        "facility_load",
    }
    assert all(item["hours"] == 24 for item in body["series"])
    assert all(item["is_contiguous"] for item in body["series"])


def test_upload_rejects_duplicate_hour(client: TestClient) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows.append(dict(rows[0]))

    result = upload_dataset(client, csv_text=build_csv(rows))

    assert result["status_code"] == 422
    assert result["body"]["error"] == "invalid_dataset"
    assert any("duplicate_hour" in issue for issue in result["body"]["issues"])


def test_upload_rejects_missing_hour(client: TestClient) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    del rows[7]

    result = upload_dataset(client, csv_text=build_csv(rows))

    assert result["status_code"] == 422
    assert any("missing_hour" in issue for issue in result["body"]["issues"])


def test_upload_accepts_missing_hour_when_allowed(client: TestClient) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    del rows[7]

    result = upload_dataset(client, csv_text=build_csv(rows), allow_gaps=True)

    assert result["status_code"] == 201
    assert result["body"]["rows_accepted"] == 23
    assert result["body"]["series"][0]["is_contiguous"] is False


def test_upload_rejects_naive_timestamps_without_timezone(client: TestClient) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    for row in rows:
        row["timestamp"] = row["timestamp"].replace("+00:00", "")

    result = upload_dataset(client, csv_text=build_csv(rows))

    assert result["status_code"] == 422
    assert any("invalid_timestamp" in issue for issue in result["body"]["issues"])


def test_upload_accepts_naive_timestamps_with_form_timezone(client: TestClient) -> None:
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    for row in rows:
        row["timestamp"] = row["timestamp"].replace("+00:00", "")

    result = upload_dataset(client, csv_text=build_csv(rows), timezone="Europe/London")

    assert result["status_code"] == 201


def test_upload_rejects_empty_file(client: TestClient) -> None:
    result = upload_dataset(client, csv_text="")
    assert result["status_code"] == 422


def test_upload_rejects_non_utf8(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("bad.csv", b"\xff\xfe\x00\x01binary", "text/csv")},
    )
    assert response.status_code == 422


def test_upload_links_to_a_facility_and_inherits_its_location(client: TestClient) -> None:
    facility = create_facility(client, location_id="facility_042")
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)

    result = upload_dataset(client, csv_text=build_csv(rows), facility_id=facility["id"])

    assert result["status_code"] == 201
    assert result["body"]["facility_id"] == facility["id"]


def test_upload_with_unknown_facility_returns_404(client: TestClient) -> None:
    result = upload_dataset(client, csv_text=sample_dataset_csv(), facility_id=uuid4())
    assert result["status_code"] == 404


def test_list_and_get_datasets(client: TestClient) -> None:
    created = upload_dataset(client, csv_text=sample_dataset_csv())["body"]

    listing = client.get("/api/v1/datasets")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created["id"]]

    single = client.get(f"/api/v1/datasets/{created['id']}")
    assert single.status_code == 200
    assert single.json()["checksum"] == created["checksum"]


def test_get_unknown_dataset_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/datasets/{uuid4()}").status_code == 404


def test_rejected_upload_persists_nothing(client: TestClient) -> None:
    """A rejected file must not leave a partial dataset behind."""
    rows = hourly_rows("electricity_price", "USD/MWh", [10.0] * 24)
    rows.append(dict(rows[0]))
    upload_dataset(client, csv_text=build_csv(rows))

    assert client.get("/api/v1/datasets").json() == []


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    from app.routers.datasets import MAX_UPLOAD_BYTES

    oversized = b"timestamp,metric,value,unit\n" + b"x" * (MAX_UPLOAD_BYTES + 1)
    response = client.post("/api/v1/datasets", files={"file": ("huge.csv", oversized, "text/csv")})

    assert response.status_code == 413
    assert "limit is" in response.json()["detail"]


def test_multi_location_upload_is_rejected(client: TestClient) -> None:
    rows = [
        *hourly_rows("electricity_price", "USD/MWh", [10.0] * 24, location="site_a"),
        *hourly_rows("electricity_price", "USD/MWh", [99.0] * 24, location="site_b"),
    ]
    result = upload_dataset(client, csv_text=build_csv(rows))

    assert result["status_code"] == 422
    assert any("multiple_locations" in issue for issue in result["body"]["issues"])


def test_datasets_can_be_filtered_by_facility(client: TestClient) -> None:
    facility = create_facility(client)
    upload_dataset(client, csv_text=sample_dataset_csv(), facility_id=facility["id"])
    upload_dataset(client, csv_text=sample_dataset_csv())

    filtered = client.get(f"/api/v1/datasets?facility_id={facility['id']}").json()
    assert len(filtered) == 1
    assert filtered[0]["facility_id"] == facility["id"]
