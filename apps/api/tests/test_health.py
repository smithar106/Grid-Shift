from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_root_advertises_docs() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_ready_reports_database_configuration() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["database_configured"] is True
