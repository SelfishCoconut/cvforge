"""FR-34: finishing a plan proposes a state change; it never makes one."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from tests.support.profile import Profile, build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import apply, queries

PLAN = {
    "summary": "Two steps.",
    "steps": [
        {"title": "Learn", "kind": "study", "done_when": "You can explain it"},
        {"title": "Build", "kind": "project", "done_when": "It runs"},
    ],
}


@pytest.fixture
def tracking(
    kb: sa.Engine, propose: Any, tmp_path: Path
) -> Iterator[tuple[TestClient, int, Profile]]:
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Haskell", "Fortran")
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=kb)
    app.state.model_factory = lambda _e: TestModel(custom_output_args=PLAN)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, posting, profile


def _plan(client: TestClient, posting: int, text: str) -> dict[str, Any]:
    gaps = client.get(f"/api/jobs/{posting}/gaps").json()
    rid = next(g["requirement_id"] for g in gaps if g["text"] == text)
    plan: dict[str, Any] = client.post(f"/api/jobs/{posting}/gaps/{rid}/plan").json()
    return plan


def _learning(kb: sa.Engine, propose: Any, entity: int) -> None:
    apply.commit_proposal(
        kb, propose({"op_type": "set_state", "entity": entity, "state": "learning"}, accept=True)
    )


def test_tracking_an_entity_not_recorded_as_learning_raises_and_creates_nothing(
    tracking: tuple[TestClient, int, Profile], kb: sa.Engine
) -> None:
    client, posting, _ = tracking
    haskell = _plan(client, posting, "Haskell")  # recorded, but only as a gap
    fortran = _plan(client, posting, "Fortran")  # not recorded at all
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    for plan in (haskell, fortran):
        step = plan["steps"][0]["id"]
        response = client.post(f"/api/plans/{plan['id']}/steps/{step}/complete")
        assert response.status_code == 409 and "learning" in response.json()["detail"]
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before
    assert client.get(f"/api/plans/{haskell['id']}").json()["steps"][0]["completed_at"] is None


def test_incomplete_steps_raise_no_proposal_and_completion_raises_one_pending_set_state(
    tracking: tuple[TestClient, int, Profile], kb: sa.Engine, propose: Any
) -> None:
    client, posting, profile = tracking
    plan = _plan(client, posting, "Haskell")
    _learning(kb, propose, profile.haskell)
    first, second = (s["id"] for s in plan["steps"])

    one = client.post(f"/api/plans/{plan['id']}/steps/{first}/complete").json()
    assert one["proposal"]["id"] is None and one["plan"]["completion_proposal_id"] is None

    done = client.post(f"/api/plans/{plan['id']}/steps/{second}/complete").json()
    proposal = done["proposal"]
    assert proposal["id"] is not None
    assert [(op["op_type"], op["classification"]) for op in proposal["operations"]] == [
        ("set_state", "new")
    ]
    with kb.connect() as conn:
        entity = queries.get_entity(conn, profile.haskell)
        record = queries.get_proposal(conn, proposal["id"])
    assert entity is not None and entity.state.value == "learning"  # not changed by completing
    assert record is not None and record.status == "open"


def test_the_proposal_goes_through_review_and_commit_like_any_other(
    tracking: tuple[TestClient, int, Profile], kb: sa.Engine, propose: Any
) -> None:
    client, posting, profile = tracking
    plan = _plan(client, posting, "Haskell")
    _learning(kb, propose, profile.haskell)
    for step in plan["steps"]:
        done = client.post(f"/api/plans/{plan['id']}/steps/{step['id']}/complete").json()
    proposal = done["proposal"]

    for op in proposal["operations"]:
        review = client.post(
            f"/api/proposals/{proposal['id']}/operations/{op['id']}/review",
            json={"decision": "accept"},
        )
        assert review.status_code == 200
    assert client.post(f"/api/proposals/{proposal['id']}/commit").status_code == 200
    with kb.connect() as conn:
        entity = queries.get_entity(conn, profile.haskell)
    assert entity is not None and entity.state.value == "confirmed"


def test_completing_again_is_idempotent_and_raises_no_second_proposal(
    tracking: tuple[TestClient, int, Profile], kb: sa.Engine, propose: Any
) -> None:
    client, posting, profile = tracking
    plan = _plan(client, posting, "Haskell")
    _learning(kb, propose, profile.haskell)
    ids = [s["id"] for s in plan["steps"]]
    for step in ids:
        client.post(f"/api/plans/{plan['id']}/steps/{step}/complete")
    again = client.post(f"/api/plans/{plan['id']}/steps/{ids[0]}/complete").json()
    with kb.connect() as conn:
        proposals = conn.execute(
            sa.text("SELECT count(*) FROM proposal WHERE summary LIKE 'learning plan%'")
        ).scalar()
    assert again["plan"]["completion_proposal_id"] is not None and proposals == 1


def test_unknown_plans_and_steps_are_404(tracking: tuple[TestClient, int, Profile]) -> None:
    client, posting, _ = tracking
    plan = _plan(client, posting, "Haskell")
    assert client.get("/api/plans/999").status_code == 404
    assert client.post("/api/plans/999/steps/1/complete").status_code == 404
    other_step = plan["steps"][0]["id"] + 999
    assert client.post(f"/api/plans/{plan['id']}/steps/{other_step}/complete").status_code in (
        404,
        409,
    )


def test_a_rejected_completion_proposal_can_be_raised_again(
    tracking: tuple[TestClient, int, Profile], kb: sa.Engine, propose: Any
) -> None:
    client, posting, profile = tracking
    plan = _plan(client, posting, "Haskell")
    _learning(kb, propose, profile.haskell)
    ids = [s["id"] for s in plan["steps"]]
    for step in ids:
        done = client.post(f"/api/plans/{plan['id']}/steps/{step}/complete").json()
    first = done["proposal"]
    for op in first["operations"]:
        client.post(
            f"/api/proposals/{first['id']}/operations/{op['id']}/review",
            json={"decision": "reject"},
        )

    again = client.post(f"/api/plans/{plan['id']}/steps/{ids[0]}/complete").json()

    assert again["proposal"]["id"] not in (None, first["id"])
