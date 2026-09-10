from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_liveness_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_unknown_route_uses_standard_error_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
