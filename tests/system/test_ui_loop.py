"""The UI's HTTP loop end to end on a real database file, with the SPA shell served (C1)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripts.demo.ui_demo import build_app, run_loop

from cvforge.kb import queries

pytestmark = pytest.mark.system


def _dist(tmp_path: Path) -> Path:
    """The built SPA when present, else a tiny stand-in shell."""
    built = Path("frontend/dist")
    if (built / "index.html").is_file():
        return built
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>CVForge</title><div id=root></div>")
    return dist


def test_chat_to_provenance_loop_keeps_invariant_three(tmp_path: Path) -> None:
    app = build_app(tmp_path / "data", _dist(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        run_loop(client)
        deep_link = client.get("/review/1")
        assert deep_link.status_code == 200
        assert "<div id=" in deep_link.text
        assert client.get("/api/health").json()["status"] == "ok"
    with app.state.engine.connect() as conn:
        assert queries.orphans(conn).clean
