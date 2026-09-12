"""The SPA is served only when it has actually been built."""

from pathlib import Path

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
    app = create_app(Settings(frontend_dist=tmp_path))
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200
