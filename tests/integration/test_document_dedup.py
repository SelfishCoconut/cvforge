"""Document candidates are classified against the knowledge base before review (FR-16).

The whole loop over HTTP: upload, extract, review, commit, then a second document.
The model is scripted; everything after it is real, including similarity search.
"""

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
from cvforge.kb import queries
from cvforge.llm.settings_store import load_settings, save_settings

pytestmark = pytest.mark.integration

DOC = "Backend engineer at Acme Logistics.\n\nBuilt a log parser in Rust.\n"
RUST = {"local_id": "s", "kind": "skill", "name": "Rust", "excerpt": "log parser in Rust"}
PARSER = {"local_id": "p", "kind": "project", "name": "Log parser", "excerpt": "Built a log parser"}
USED = {"src": "s", "rel": "used_in", "dst": "p", "excerpt": "Built a log parser in Rust."}


@pytest.fixture
def docs(kb: sa.Engine, tmp_path: Path) -> Iterator[TestClient]:
    save_settings(kb, load_settings(kb).model_copy(update={"similarity_threshold": 0.5}))
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")
    app = create_app(settings, engine=kb, embedder=FakeEmbeddingProvider())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _extract(client: TestClient, text: str, output: dict[str, Any]) -> dict[str, Any]:
    client.app.state.model_factory = lambda _e: TestModel(custom_output_args=output)  # type: ignore[attr-defined]
    upload = client.post("/api/documents", files={"file": ("cv.md", text.encode())})
    response = client.post(f"/api/documents/{upload.json()['source_id']}/extract")
    body: dict[str, Any] = response.json()
    return body


def _commit(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    proposal = body["proposal"]
    for op in proposal["operations"]:
        url = f"/api/proposals/{proposal['id']}/operations/{op['id']}/review"
        client.post(url, json={"decision": "accept"}).raise_for_status()
    response = client.post(f"/api/proposals/{proposal['id']}/commit")
    response.raise_for_status()
    committed: dict[str, Any] = response.json()
    return committed


def _kinds(body: dict[str, Any]) -> list[str]:
    return [op["classification"] for op in body["proposal"]["operations"]]


def test_a_wholly_new_candidate_is_new(docs: TestClient) -> None:
    body = _extract(docs, DOC, {"facts": [RUST], "edges": []})

    assert _kinds(body) == ["new"]


def test_a_candidate_identical_to_an_entity_is_known_and_names_it(docs: TestClient) -> None:
    first = _commit(docs, _extract(docs, DOC, {"facts": [RUST], "edges": []}))
    existing = first["entity_ids"]["0"]

    second = _extract(
        docs, "I use Rust daily.\n", {"facts": [{**RUST, "excerpt": "Rust"}], "edges": []}
    )

    (op,) = second["proposal"]["operations"]
    assert op["classification"] == "known" and op["target_id"] == existing


def test_a_differently_worded_candidate_is_a_duplicate_and_names_it(docs: TestClient) -> None:
    first = _commit(docs, _extract(docs, DOC, {"facts": [RUST], "edges": []}))
    existing = first["entity_ids"]["0"]
    reworded = {**RUST, "name": "Rust language", "excerpt": "Rust"}

    second = _extract(docs, "I use Rust daily.\n", {"facts": [reworded], "edges": []})

    (op,) = second["proposal"]["operations"]
    assert op["classification"] == "duplicate" and op["target_id"] == existing


def test_ingesting_the_same_document_twice_creates_nothing_new(
    docs: TestClient, kb: sa.Engine
) -> None:
    output = {"facts": [RUST, PARSER], "edges": [USED]}
    _commit(docs, _extract(docs, DOC, output))
    with kb.connect() as conn:
        before = queries.table_counts(conn)

    second = _extract(docs, DOC, output)
    _commit(docs, second)

    assert _kinds(second)[:2] == ["known", "known"]
    with kb.connect() as conn:
        after = queries.table_counts(conn)
    assert (after["entity"], after["edge"]) == (before["entity"], before["edge"])


def test_conflicting_employment_dates_classify_as_a_conflict_naming_the_edge(
    docs: TestClient, kb: sa.Engine
) -> None:
    facts = [
        {
            "local_id": "r",
            "kind": "role",
            "name": "Backend engineer",
            "excerpt": "Backend engineer",
        },
        {"local_id": "o", "kind": "organization", "name": "Acme", "excerpt": "Acme Logistics"},
    ]
    edge = {
        "src": "r",
        "rel": "at_organization",
        "dst": "o",
        "excerpt": "Backend engineer at Acme Logistics",
        "started_at": "2019-01-01",
        "ended_at": "2022-01-01",
    }
    first = _commit(docs, _extract(docs, DOC, {"facts": facts, "edges": [edge]}))
    role, org = first["entity_ids"]["0"], first["entity_ids"]["1"]
    contradicting = {**edge, "src": role, "dst": org, "started_at": "2020-06-01"}

    second = _extract(docs, DOC, {"facts": [], "edges": [contradicting]})

    (op,) = second["proposal"]["operations"]
    assert op["classification"] == "conflict" and op["target_kind"] == "edge"
