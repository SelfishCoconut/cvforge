"""FR-03 (every fact bound to evidence) and FR-12 (conversations as citable sources)."""

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply, queries, schema
from cvforge.kb.models import ProposalDraft
from cvforge.kb.vocab import SourceKind, TargetKind

Propose = Callable[..., int]


def _kb_rows(kb: sa.Engine) -> dict[str, int]:
    with kb.connect() as conn:
        counts = queries.table_counts(conn)
    return {k: counts[k] for k in ("entity", "edge", "assertion")}


def test_every_created_entity_and_edge_has_assertions(kb: sa.Engine, propose: Propose) -> None:
    result = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "organization", "name": "Acme"},
            {"op_type": "add_edge", "src": {"op": 0}, "rel": "at_organization", "dst": {"op": 1}},
            accept=True,
        ),
    )
    with kb.connect() as conn:
        report = queries.orphans(conn)
        rust = queries.provenance(conn, TargetKind.ENTITY, result.entity_ids[0])
    assert report.clean
    assert {p.field for p in rust} == {None, "name", "state"}


def test_a_failing_entity_write_leaves_nothing_behind(kb: sa.Engine, propose: Propose) -> None:
    """An entity whose assertion cannot be written is not written either."""
    proposal = propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True)
    with kb.begin() as conn:  # sabotage: the cited evidence disappears before commit
        conn.execute(sa.delete(schema.evidence))
    with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"):
        apply.commit_proposal(kb, proposal)
    assert _kb_rows(kb) == {"entity": 0, "edge": 0, "assertion": 0}


def test_a_failing_edge_write_leaves_nothing_behind(kb: sa.Engine, propose: Propose) -> None:
    ids = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            accept=True,
        ),
    ).entity_ids
    before = _kb_rows(kb)
    source = apply.record_source(kb, SourceKind.CONVERSATION, "later chat")
    doomed = apply.record_evidence(kb, source, "message:2", "Rust was used in the parser.")
    edge = {"op_type": "add_edge", "src": ids[0], "rel": "used_in", "dst": ids[1]}
    proposal = propose({**edge, "evidence_id": doomed}, accept=True)
    with kb.begin() as conn:  # sabotage: only the edge's own evidence disappears
        conn.execute(sa.delete(schema.evidence).where(schema.evidence.c.id == doomed))
    with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"):
        apply.commit_proposal(kb, proposal)
    assert _kb_rows(kb) == before


def test_the_api_resolves_a_fact_to_source_locator_and_excerpt(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    result = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True)
    )
    response = client.get(f"/api/provenance/entity/{result.entity_ids[0]}")
    assert response.status_code == 200
    existence = next(p for p in response.json() if p["field"] is None)
    assert existence["source_kind"] == "conversation"
    assert existence["locator"] == "message:1"
    assert existence["excerpt"] == "I built a parser in Rust at Acme."


def test_provenance_of_an_unknown_target_is_404(client: TestClient) -> None:
    assert client.get("/api/provenance/entity/999").status_code == 404


# --- FR-12: conversations ---------------------------------------------------------


def test_a_chat_message_is_a_source_and_an_evidence_row(kb: sa.Engine) -> None:
    source = apply.record_source(kb, SourceKind.CONVERSATION, "chat 2026-09-21")
    evidence = apply.record_evidence(kb, source, "message:7", "I mentor two juniors.")
    with kb.connect() as conn:
        row = conn.execute(sa.select(schema.evidence).where(schema.evidence.c.id == evidence)).one()
        kind = conn.execute(sa.select(schema.source.c.kind).where(schema.source.c.id == source))
    assert (row.source_id, row.locator, row.excerpt) == (
        source,
        "message:7",
        "I mentor two juniors.",
    )
    assert kind.scalar_one() == "conversation"


def test_an_operation_citing_missing_evidence_never_reaches_review(kb: sa.Engine) -> None:
    source = apply.record_source(kb, SourceKind.CONVERSATION, "chat")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "orphan",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "op_type": "create_entity",
                        "kind": "skill",
                        "name": "Go",
                        "evidence_id": 42,
                    },
                    "classification": "new",
                }
            ],
        }
    )
    with pytest.raises(apply.NotFoundError, match="evidence 42"):
        apply.record_proposal(kb, draft)
    with kb.connect() as conn:
        assert queries.table_counts(conn)["proposal"] == 0


def test_evidence_for_a_missing_source_is_refused(kb: sa.Engine) -> None:
    with pytest.raises(apply.NotFoundError, match="source 5"):
        apply.record_evidence(kb, 5, "message:1", "text")


def test_the_evidence_foreign_key_is_enforced_by_the_database(kb: sa.Engine) -> None:
    """Not just by apply.py: a raw insert with a dangling source_id is refused."""
    with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"), kb.begin() as conn:
        conn.execute(sa.insert(schema.evidence).values(source_id=5, locator="m", excerpt="x"))
