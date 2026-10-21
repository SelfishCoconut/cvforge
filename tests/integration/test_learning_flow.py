"""Gap -> plan -> track -> proposal -> review -> commit, over a migrated database file (M7)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from tests.support.profile import build_profile_with, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import apply, queries

pytestmark = pytest.mark.integration

PLAN = {
    "summary": "Two steps.",
    "steps": [
        {"title": "Learn", "kind": "study", "done_when": "You can explain it"},
        {"title": "Build", "kind": "project", "done_when": "It runs"},
    ],
}


def test_a_gap_becomes_a_confirmed_skill_only_through_review(tmp_path: Path, open_db: Any) -> None:
    engine = open_db(tmp_path / "cvforge.db")
    profile = build_profile_with(engine)
    posting = matched_posting(engine, "Haskell")
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=engine)
    app.state.model_factory = lambda _e: TestModel(custom_output_args=PLAN)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        rid = client.get(f"/api/jobs/{posting}/gaps").json()[0]["requirement_id"]
        plan = client.post(f"/api/jobs/{posting}/gaps/{rid}/plan").json()
        assert plan["entity_id"] == profile.haskell
        steps = [s["id"] for s in plan["steps"]]
        assert client.post(f"/api/plans/{plan['id']}/steps/{steps[0]}/complete").status_code == 409

        proposal = _record_learning(engine, profile.haskell)
        apply.commit_proposal(engine, proposal)
        for step in steps:
            done = client.post(f"/api/plans/{plan['id']}/steps/{step}/complete").json()
        pending = done["proposal"]
        with engine.connect() as conn:
            assert queries.get_entity(conn, profile.haskell).state.value == "learning"  # type: ignore[union-attr]
        for op in pending["operations"]:
            client.post(
                f"/api/proposals/{pending['id']}/operations/{op['id']}/review",
                json={"decision": "accept"},
            )
        assert client.post(f"/api/proposals/{pending['id']}/commit").status_code == 200
    with engine.connect() as conn:
        assert queries.get_entity(conn, profile.haskell).state.value == "confirmed"  # type: ignore[union-attr]


def _record_learning(engine: Any, entity_id: int) -> int:
    from cvforge.kb.models import ProposalInput
    from cvforge.kb.vocab import SourceKind

    source = apply.record_source(engine, SourceKind.CONVERSATION, "chat")
    evidence = apply.record_evidence(engine, source, "message:1", "I started learning Haskell.")
    draft = ProposalInput.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "learning",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "op_type": "set_state",
                        "entity": entity_id,
                        "state": "learning",
                        "evidence_id": evidence,
                    },
                }
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    for op in record.operations if record else []:
        apply.review_operation(engine, op.id, "accept")
    return proposal
