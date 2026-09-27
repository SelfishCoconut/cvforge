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
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>CVForge</title><div id='root'></div>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log('cvforge')", encoding="utf-8")
    return dist


def _settings(built_dist: Path) -> Settings:
    """Settings whose knowledge base lives beside the dist directory, never in ./data."""
    return Settings(frontend_dist=built_dist, data_dir=built_dist.parent / "data")


def test_spa_and_api_coexist(built_dist: Path) -> None:
    """The static mount at / must not shadow the JSON API under /api."""
    with TestClient(create_app(_settings(built_dist)), base_url="http://127.0.0.1") as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "CVForge" in root.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"


def test_openapi_schema_is_served(built_dist: Path) -> None:
    with TestClient(create_app(_settings(built_dist)), base_url="http://127.0.0.1") as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/api/health" in schema.json()["paths"]
