"""`POST/GET /api/jobs/{id}/match` store and return one verdict per requirement."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, queries
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage


def _commit(kb: sa.Engine, propose: Any, *payloads: dict[str, Any]) -> dict[int, int]:
    return apply.commit_proposal(kb, propose(*payloads, accept=True)).entity_ids


@pytest.fixture
def matching(kb: sa.Engine, propose: Any, tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    ids = _commit(
        kb,
        propose,
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
        {"op_type": "create_entity", "kind": "project", "name": "Parser"},
    )
    _commit(kb, propose, {"op_type": "add_edge", "src": ids[0], "rel": "used_in", "dst": ids[1]})
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(
        kb, page, JobAnalysis(required_skills=["Rust", "Fortran"], preferred_skills=["Go"])
    ).id
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=kb, embedder=FakeEmbeddingProvider())
    app.state.model_factory = lambda _e: TestModel(
        custom_output_args={"entity_ids": [], "rationale": ""}
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, posting


def test_running_a_match_returns_a_verdict_for_every_requirement(
    matching: tuple[TestClient, int],
) -> None:
    client, posting = matching
    response = client.post(f"/api/jobs/{posting}/match")

    assert response.status_code == 200
    rows = response.json()
    assert [(r["text"], r["verdict"]) for r in rows] == [
        ("Rust", "satisfied"),
        ("Fortran", "gap"),
        ("Go", "gap"),
    ]
    assert rows[0]["support"] and rows[1]["support"] == []


def test_the_stored_verdicts_read_back_and_rerunning_replaces_them(
    matching: tuple[TestClient, int],
) -> None:
    client, posting = matching
    assert client.get(f"/api/jobs/{posting}/match").json() == []
    first = client.post(f"/api/jobs/{posting}/match").json()
    client.post(f"/api/jobs/{posting}/match")
    assert client.get(f"/api/jobs/{posting}/match").json() == first


def test_an_unknown_posting_is_404(matching: tuple[TestClient, int]) -> None:
    client, _ = matching
    assert client.post("/api/jobs/999/match").status_code == 404
    assert client.get("/api/jobs/999/match").status_code == 404


def test_matching_writes_no_knowledge(matching: tuple[TestClient, int], kb: sa.Engine) -> None:
    client, posting = matching
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    client.post(f"/api/jobs/{posting}/match")
    with kb.connect() as conn:
        after = queries.table_counts(conn)
    for table in ("entity", "edge", "assertion", "proposal"):
        assert after[table] == before[table]


def test_support_carries_entity_and_evidence_and_gaps_have_none(
    matching: tuple[TestClient, int],
) -> None:
    client, posting = matching
    rows = client.post(f"/api/jobs/{posting}/match").json()

    (support,) = rows[0]["support"]
    assert support["name"] == "Rust" and support["archived"] is False
    assert support["evidence"] and {"locator", "excerpt", "source_kind"} <= set(
        support["evidence"][0]
    )
    assert rows[1]["support"] == []


def test_the_gap_report_endpoint_lists_the_unbacked_requirements(
    matching: tuple[TestClient, int],
) -> None:
    client, posting = matching
    assert client.get(f"/api/jobs/{posting}/gaps").json() == []
    client.post(f"/api/jobs/{posting}/match")
    gaps = client.get(f"/api/jobs/{posting}/gaps").json()

    assert [(g["text"], g["verdict"]) for g in gaps] == [("Fortran", "gap"), ("Go", "gap")]
    assert client.get("/api/jobs/999/gaps").status_code == 404


def test_matching_still_works_when_no_model_can_be_built(
    matching: tuple[TestClient, int],
) -> None:
    client, posting = matching

    def no_model(_engine: object) -> object:
        raise RuntimeError("no provider configured")

    client.app.state.model_factory = no_model  # type: ignore[attr-defined]
    response = client.post(f"/api/jobs/{posting}/match")
    assert response.status_code == 200 and response.json()[0]["verdict"] == "satisfied"
