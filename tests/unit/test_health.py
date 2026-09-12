"""The /api/health contract."""

from fastapi.testclient import TestClient

import cvforge


def test_health_reports_ok_and_the_running_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": cvforge.__version__}


def test_health_is_namespaced_under_api(client: TestClient) -> None:
    """The bare /health path must not exist — every JSON route lives under /api."""
    assert client.get("/health").status_code == 404
