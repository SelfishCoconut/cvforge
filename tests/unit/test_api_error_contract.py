"""The HTTP status contract of the write path, pinned status by status.

`cvforge.api.errors` documents the mapping; these tests hold each row of it. Before
they existed, changing 409 to 404 or 500 for any of these passed every test.
"""

from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply, queries

Propose = Callable[..., int]

SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def _commit_url(proposal: int) -> str:
    return f"/api/proposals/{proposal}/commit"


def test_committing_an_already_committed_proposal_is_a_409(
    client: TestClient, propose: Propose
) -> None:
    proposal = propose(SKILL, accept=True)
    assert client.post(_commit_url(proposal)).status_code == 200
    again = client.post(_commit_url(proposal))
    assert again.status_code == 409
    assert "already committed" in again.json()["detail"]


def test_committing_with_an_operation_still_pending_is_a_409(
    client: TestClient, propose: Propose
) -> None:
    response = client.post(_commit_url(propose(SKILL)))
    assert response.status_code == 409
    assert "pending" in response.json()["detail"]


def test_an_operation_this_version_cannot_apply_is_a_422(
    client: TestClient, propose: Propose
) -> None:
    merge = propose({"op_type": "merge_duplicate", "keep_id": 1, "merge_id": 2}, accept=True)
    assert client.post(_commit_url(merge)).status_code == 422


def test_a_commit_the_database_rejects_is_a_409_that_writes_nothing(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    """A dishonest `new` classification for an edge that exists trips the UNIQUE constraint."""
    first = apply.commit_proposal(
        kb,
        propose(
            SKILL,
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
            accept=True,
        ),
    )
    rust, parser = first.entity_ids[0], first.entity_ids[1]
    duplicate_edge = {"op_type": "add_edge", "src": rust, "rel": "used_in", "dst": parser}
    proposal = propose(duplicate_edge, accept=True)
    with kb.connect() as conn:
        before = queries.table_counts(conn)

    response = client.post(_commit_url(proposal))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "nothing was written" in detail
    assert "UNIQUE constraint failed" in detail
    assert "INSERT INTO" not in detail  # the driver's reason, not the SQL and its parameters
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before
