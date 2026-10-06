"""Read queries behind the review UI: the proposal list and evidence lookup."""

from collections.abc import Callable, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply, queries
from cvforge.kb.vocab import ProposalStatus

Propose = Callable[..., int]

SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}
PROJECT = {"op_type": "create_entity", "kind": "project", "name": "Parser"}
ORG = {"op_type": "create_entity", "kind": "organization", "name": "Acme"}


@pytest.fixture
def conn_with_two_proposals(kb: sa.Engine, propose: Propose) -> Iterator[sa.Connection]:
    """Proposal 1 is open with two pending operations; proposal 2 is committed."""
    propose(SKILL, PROJECT)
    second = propose(ORG, accept=True)
    apply.commit_proposal(kb, second)
    with kb.connect() as conn:
        yield conn


def test_list_proposals_newest_first_with_counts(conn_with_two_proposals: sa.Connection) -> None:
    rows = queries.list_proposals(conn_with_two_proposals)
    assert [r.id for r in rows] == [2, 1]
    assert rows[1].operation_count == 2 and rows[1].pending_count == 2
    assert rows[0].operation_count == 1 and rows[0].pending_count == 0
    assert rows[0].applied_at is not None and rows[1].applied_at is None


def test_list_proposals_filters_by_status(conn_with_two_proposals: sa.Connection) -> None:
    assert [
        r.status
        for r in queries.list_proposals(conn_with_two_proposals, status=ProposalStatus.OPEN)
    ] == ["open"]


def test_list_proposals_without_operations_counts_zero(kb: sa.Engine, evidence_id: int) -> None:
    with kb.begin() as conn:
        conn.execute(
            sa.text(
                "insert into proposal (origin, source_id, status, summary, created_at)"
                " values ('chat', 1, 'open', 'empty', current_timestamp)"
            )
        )
    with kb.connect() as conn:
        (row,) = queries.list_proposals(conn)
    assert row.operation_count == 0 and row.pending_count == 0


def test_get_evidence_resolves_source(conn_with_two_proposals: sa.Connection) -> None:
    ev = queries.get_evidence(conn_with_two_proposals, 1)
    assert ev is not None and ev.excerpt and ev.source_kind == "conversation"


def test_get_evidence_missing_is_none(conn_with_two_proposals: sa.Connection) -> None:
    assert queries.get_evidence(conn_with_two_proposals, 9999) is None


def test_api_lists_proposals(client: TestClient, propose: Propose) -> None:
    propose(SKILL)
    propose(PROJECT)
    body = client.get("/api/proposals").json()
    assert [p["id"] for p in body] == [2, 1]
    assert client.get("/api/proposals", params={"status": "open"}).status_code == 200
    assert client.get("/api/proposals", params={"status": "committed"}).json() == []
    assert client.get("/api/proposals", params={"status": "bogus"}).status_code == 422


def test_api_resolves_evidence(client: TestClient, evidence_id: int) -> None:
    body = client.get(f"/api/evidence/{evidence_id}").json()
    assert body["excerpt"] == "I built a parser in Rust at Acme."
    assert body["source_kind"] == "conversation"
    missing = client.get("/api/evidence/9999")
    assert missing.status_code == 404 and "detail" in missing.json()
