"""FR-09: each operation is reviewed independently; FR-06 c3: no write outside a commit."""

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply, queries

Propose = Callable[..., int]

SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}
PROJECT = {"op_type": "create_entity", "kind": "project", "name": "Parser"}
ORG = {"op_type": "create_entity", "kind": "organization", "name": "Acme"}


def _ops(kb: sa.Engine, proposal_id: int) -> list[queries.OperationRecord]:
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    assert record is not None
    return record.operations


def test_rejecting_one_operation_leaves_its_siblings_untouched(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose(SKILL, PROJECT, ORG)
    first, second, _third = _ops(kb, proposal)
    apply.review_operation(kb, first.id, "accept")
    apply.review_operation(kb, second.id, "reject")
    assert [op.status for op in _ops(kb, proposal)] == ["accepted", "rejected", "pending"]


def test_an_edit_is_stored_beside_the_original(kb: sa.Engine, propose: Propose) -> None:
    proposal = propose(SKILL)
    (op,) = _ops(kb, proposal)
    edited = {**op.payload, "name": "Rust (systems)"}
    apply.review_operation(kb, op.id, "edit", edited)
    (after,) = _ops(kb, proposal)
    assert after.status == "edited"
    assert after.payload["name"] == "Rust"
    assert after.edited_payload is not None and after.edited_payload["name"] == "Rust (systems)"


def test_the_commit_applies_the_edited_payload(kb: sa.Engine, propose: Propose) -> None:
    proposal = propose(SKILL)
    (op,) = _ops(kb, proposal)
    apply.review_operation(kb, op.id, "edit", {**op.payload, "name": "Rust (systems)"})
    result = apply.commit_proposal(kb, proposal)
    with kb.connect() as conn:
        stored = queries.get_entity(conn, result.entity_ids[0])
    assert stored is not None and stored.name == "Rust (systems)"


def test_only_accepted_and_edited_operations_are_applied(kb: sa.Engine, propose: Propose) -> None:
    proposal = propose(SKILL, PROJECT, ORG)
    first, second, third = _ops(kb, proposal)
    apply.review_operation(kb, first.id, "accept")
    apply.review_operation(kb, second.id, "reject")
    apply.review_operation(kb, third.id, "edit", {**third.payload, "name": "Acme Corp"})
    result = apply.commit_proposal(kb, proposal)
    with kb.connect() as conn:
        names = [e.name for e in queries.list_entities(conn)]
    assert names == ["Rust", "Acme Corp"]
    assert result.applied_operation_ids == [first.id, third.id]
    assert [op.status for op in _ops(kb, proposal)] == ["applied", "rejected", "applied"]


def test_a_pending_operation_blocks_the_commit(kb: sa.Engine, propose: Propose) -> None:
    proposal = propose(SKILL, PROJECT)
    first, _ = _ops(kb, proposal)
    apply.review_operation(kb, first.id, "accept")
    with pytest.raises(apply.OperationsPendingError):
        apply.commit_proposal(kb, proposal)
    with kb.connect() as conn:
        assert queries.list_entities(conn) == []


def test_an_edit_cannot_change_the_operation_type(kb: sa.Engine, propose: Propose) -> None:
    (op,) = _ops(kb, propose(SKILL))
    with pytest.raises(apply.InvalidEditError, match="cannot change"):
        apply.review_operation(
            kb,
            op.id,
            "edit",
            {"op_type": "set_state", "entity": 1, "state": "gap", "evidence_id": 1},
        )


def test_an_invalid_edit_is_refused(kb: sa.Engine, propose: Propose) -> None:
    (op,) = _ops(kb, propose(SKILL))
    with pytest.raises(apply.InvalidEditError, match="invalid"):
        apply.review_operation(kb, op.id, "edit", {**op.payload, "kind": "hobby"})


def test_edit_without_a_payload_and_payload_without_edit_are_refused(
    kb: sa.Engine, propose: Propose
) -> None:
    (op,) = _ops(kb, propose(SKILL))
    with pytest.raises(apply.InvalidEditError):
        apply.review_operation(kb, op.id, "edit")
    with pytest.raises(apply.InvalidEditError):
        apply.review_operation(kb, op.id, "accept", op.payload)


def test_a_committed_proposal_cannot_be_reviewed_or_committed_again(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose(SKILL, accept=True)
    apply.commit_proposal(kb, proposal)
    (op,) = _ops(kb, proposal)
    with pytest.raises(apply.ProposalNotOpenError):
        apply.review_operation(kb, op.id, "reject")
    with pytest.raises(apply.ProposalNotOpenError):
        apply.commit_proposal(kb, proposal)


def test_unknown_proposal_and_operation_are_not_found(kb: sa.Engine) -> None:
    with pytest.raises(apply.NotFoundError):
        apply.commit_proposal(kb, 404)
    with pytest.raises(apply.NotFoundError):
        apply.review_operation(kb, 404, "accept")


def test_merge_duplicate_is_refused_until_m1b(kb: sa.Engine, propose: Propose) -> None:
    proposal = propose({"op_type": "merge_duplicate", "keep_id": 1, "merge_id": 2}, accept=True)
    with pytest.raises(apply.UnsupportedOperationError, match="M1b"):
        apply.commit_proposal(kb, proposal)


# --- the same flow over HTTP ------------------------------------------------------


def test_review_and_commit_over_the_api(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose(SKILL, PROJECT)
    body = client.get(f"/api/proposals/{proposal}").json()
    first, second = body["operations"]
    url = f"/api/proposals/{proposal}/operations"
    assert (
        client.post(f"{url}/{first['id']}/review", json={"decision": "accept"}).status_code == 200
    )
    assert client.post(f"/api/proposals/{proposal}/commit").status_code == 409  # one still pending
    reviewed = client.post(f"{url}/{second['id']}/review", json={"decision": "reject"})
    assert [op["status"] for op in reviewed.json()["operations"]] == ["accepted", "rejected"]
    committed = client.post(f"/api/proposals/{proposal}/commit")
    assert committed.status_code == 200
    assert committed.json()["applied_operation_ids"] == [first["id"]]
    assert [e["name"] for e in client.get("/api/entities").json()] == ["Rust"]


def test_api_refuses_an_operation_from_another_proposal(
    client: TestClient, propose: Propose, kb: sa.Engine
) -> None:
    mine, other = propose(SKILL), propose(PROJECT)
    (theirs,) = _ops(kb, other)
    response = client.post(
        f"/api/proposals/{mine}/operations/{theirs.id}/review", json={"decision": "accept"}
    )
    assert response.status_code == 404


def test_api_maps_refusals_to_status_codes(
    client: TestClient, propose: Propose, kb: sa.Engine
) -> None:
    proposal = propose(SKILL)
    (op,) = _ops(kb, proposal)
    bad_edit = client.post(
        f"/api/proposals/{proposal}/operations/{op.id}/review",
        json={"decision": "edit", "edited_payload": {**op.payload, "kind": "hobby"}},
    )
    assert bad_edit.status_code == 422
    assert client.get("/api/proposals/999").status_code == 404
    assert client.post("/api/proposals/999/commit").status_code == 404
