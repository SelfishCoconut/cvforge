"""Posting -> match -> evidence -> gaps against a real, migrated database file (M4)."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply
from cvforge.kb.models import ProposalInput
from cvforge.kb.vocab import SourceKind
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

pytestmark = pytest.mark.integration

OpenDb = Callable[..., sa.Engine]


def _seed(engine: sa.Engine) -> None:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "I used Rust in a log parser.")

    def op(seq: int, **payload: object) -> dict[str, object]:
        return {"seq": seq, "payload": {"evidence_id": evidence, **payload}}

    draft = ProposalInput.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "s",
            "operations": [
                op(0, op_type="create_entity", kind="skill", name="Rust"),
                op(1, op_type="create_entity", kind="project", name="Log parser"),
                op(2, op_type="add_edge", src={"op": 0}, rel="used_in", dst={"op": 1}),
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id FROM operation WHERE proposal_id = :p"), {"p": proposal}
        )
        ids = [r.id for r in rows]
    for op_id in ids:
        apply.review_operation(engine, op_id, "accept")
    apply.commit_proposal(engine, proposal)


def test_match_evidence_and_gaps_over_a_migrated_database(tmp_path: Path, open_db: OpenDb) -> None:
    engine = open_db(tmp_path / "cvforge.db")
    _seed(engine)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(engine, page, JobAnalysis(required_skills=["Rust", "Fortran"])).id
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=engine, embedder=FakeEmbeddingProvider())
    app.state.model_factory = lambda _e: TestModel(
        custom_output_args={"entity_ids": [], "rationale": ""}
    )

    with TestClient(app, base_url="http://127.0.0.1") as client:
        rows = client.post(f"/api/jobs/{posting}/match").json()
        gaps = client.get(f"/api/jobs/{posting}/gaps").json()
        entity = client.get(f"/api/entities/{rows[0]['support'][0]['entity_id']}")

    assert [(r["text"], r["verdict"]) for r in rows] == [
        ("Rust", "satisfied"),
        ("Fortran", "gap"),
    ]
    assert rows[0]["support"][0]["evidence"][0]["excerpt"] == "I used Rust in a log parser."
    assert [g["text"] for g in gaps] == ["Fortran"]
    assert entity.status_code == 200
