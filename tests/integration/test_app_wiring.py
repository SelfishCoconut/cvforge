"""The assembled application against a real on-disk dist directory."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def built_dist(tmp_path: Path) -> Path:
    """A minimal but real built-SPA directory."""
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>CVForge</title><div id='root'></div>", encoding="utf-8"
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('cvforge')", encoding="utf-8")
    return tmp_path


def test_spa_and_api_coexist(built_dist: Path) -> None:
    """The static mount at / must not shadow the JSON API under /api."""
    with TestClient(create_app(Settings(frontend_dist=built_dist))) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "CVForge" in root.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"


def test_openapi_schema_is_served(built_dist: Path) -> None:
    with TestClient(create_app(Settings(frontend_dist=built_dist))) as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/api/health" in schema.json()["paths"]
