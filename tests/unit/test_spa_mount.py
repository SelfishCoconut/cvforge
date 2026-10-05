"""The SPA is served only when it has actually been built."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cvforge.app import _mount_spa, create_app
from cvforge.config import Settings


def test_mount_is_skipped_when_nothing_is_built(tmp_path: Path) -> None:
    app = FastAPI()
    assert _mount_spa(app, tmp_path) is False


def test_mount_happens_when_index_html_exists(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>CVForge</title>", encoding="utf-8")
    app = FastAPI()
    assert _mount_spa(app, tmp_path) is True


def test_root_returns_404_without_a_build(tmp_path: Path) -> None:
    app = create_app(Settings(frontend_dist=tmp_path, data_dir=tmp_path / "data"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200


@pytest.fixture
def spa_client(tmp_path: Path) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (dist / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app(Settings(frontend_dist=dist, data_dir=tmp_path / "data"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_deep_link_serves_index(spa_client: TestClient) -> None:
    r = spa_client.get("/review/3")
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_real_asset_still_served(spa_client: TestClient) -> None:
    assert spa_client.get("/assets/a.js").status_code == 200


def test_unknown_api_path_is_still_404_json(spa_client: TestClient) -> None:
    r = spa_client.get("/api/nope")
    assert r.status_code == 404
    assert "text/html" not in r.headers["content-type"]


def test_missing_asset_file_is_404(spa_client: TestClient) -> None:
    assert spa_client.get("/assets/missing.js").status_code == 404


def test_non_404_errors_are_not_masked(spa_client: TestClient) -> None:
    assert spa_client.post("/review/3").status_code == 405
