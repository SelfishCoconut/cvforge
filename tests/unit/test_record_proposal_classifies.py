"""`record_proposal` computes the classification itself; the caller cannot state one (ADR-0009)."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from cvforge.kb import apply, queries, schema
from cvforge.kb.models import OperationInput, ProposalInput
from cvforge.kb.vocab import Classification, EntityKind, SourceKind

Propose = Callable[..., int]
OpenDb = Callable[..., sa.Engine]
Forge = Callable[..., None]

GO = {"op_type": "create_entity", "kind": "skill", "name": "Go"}
RUST = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def _create(kb: sa.Engine, propose: Propose, payload: dict[str, str]) -> int:
    return apply.commit_proposal(kb, propose(payload, accept=True)).entity_ids[0]


def _operation(kb: sa.Engine, proposal_id: int) -> queries.OperationRecord:
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    assert record is not None
    return record.operations[0]


def _input(source_id: int, evidence_id: int, payload: dict[str, str]) -> ProposalInput:
    return ProposalInput.model_validate(
        {
            "origin": "chat",
            "source_id": source_id,
            "summary": "test",
            "operations": [{"seq": 0, "payload": {"evidence_id": evidence_id, **payload}}],
        }
    )


def _source_of(kb: sa.Engine, evidence_id: int) -> int:
    with kb.connect() as conn:
        found = conn.execute(
            sa.select(schema.evidence.c.source_id).where(schema.evidence.c.id == evidence_id)
        ).scalar_one()
    return int(found)


def test_a_caller_cannot_state_a_classification_or_a_target() -> None:
    payload = {"op_type": "create_entity", "kind": "skill", "name": "Go", "evidence_id": 1}
    for forged in ({"classification": "known"}, {"target_kind": "entity"}, {"target_id": 7}):
        with pytest.raises(ValidationError):
            OperationInput.model_validate({"seq": 0, "payload": payload, **forged})
    with pytest.raises(ValidationError):
        ProposalInput.model_validate(
            {
                "origin": "chat",
                "source_id": 1,
                "summary": "x",
                "operations": [],
                "classification": "new",
            }
        )


def test_the_audit_forgery_cannot_be_recorded(kb: sa.Engine, propose: Propose) -> None:
    kubernetes = _create(
        kb, propose, {"op_type": "create_entity", "kind": "skill", "name": "Kubernetes"}
    )
    operation = _operation(kb, propose(GO))
    assert operation.classification == Classification.NEW.value
    assert operation.target_id is None
    assert kubernetes != operation.target_id


def test_a_known_entity_is_computed_names_its_target_and_adds_only_an_assertion(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _create(kb, propose, RUST)
    again = propose({**RUST, "name": "  rust "}, accept=True)
    operation = _operation(kb, again)
    assert (operation.classification, operation.target_id) == ("known", rust)
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    apply.commit_proposal(kb, again)
    with kb.connect() as conn:
        after = queries.table_counts(conn)
    assert after["entity"] == before["entity"]
    assert after["assertion"] == before["assertion"] + 1


def test_a_stale_known_is_refused_at_commit_with_nothing_written(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _create(kb, propose, RUST)
    stale = propose({**RUST}, accept=True)  # recorded as `known` against `rust`
    rename = {"op_type": "update_field", "entity_id": rust, "field": "name", "value": "Ferrous"}
    apply.commit_proposal(kb, propose(rename, accept=True))
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    with pytest.raises(apply.StaleClassificationError):
        apply.commit_proposal(kb, stale)
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before
        record = queries.get_proposal(conn, stale)
    assert record is not None
    assert record.status == "open"


def test_a_known_whose_target_kind_differs_from_the_payload_is_refused_at_commit(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _create(kb, propose, RUST)
    org = _create(kb, propose, {"op_type": "create_entity", "kind": "organization", "name": "Acme"})
    stale = propose(RUST, accept=True)
    with kb.begin() as conn:  # a forged row, as only a bug or a tampered database could produce
        conn.execute(
            sa.update(schema.operation)
            .where(schema.operation.c.proposal_id == stale)
            .values(target_id=org)
        )
    assert rust != org
    with pytest.raises(apply.StaleClassificationError):
        apply.commit_proposal(kb, stale)


def test_a_known_update_field_whose_target_is_not_the_payloads_entity_is_refused(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _create(kb, propose, RUST)
    go = _create(kb, propose, GO)
    same = {"op_type": "update_field", "entity_id": rust, "field": "name", "value": "Rust"}
    proposal = propose(same, accept=True)
    assert _operation(kb, proposal).classification == "known"
    with kb.begin() as conn:
        conn.execute(
            sa.update(schema.operation)
            .where(schema.operation.c.proposal_id == proposal)
            .values(target_id=go)
        )
    with pytest.raises(apply.StaleClassificationError):
        apply.commit_proposal(kb, proposal)


def test_a_known_edge_whose_triple_changed_is_refused(kb: sa.Engine, propose: Propose) -> None:
    rust = _create(kb, propose, RUST)
    acme = _create(
        kb, propose, {"op_type": "create_entity", "kind": "organization", "name": "Acme"}
    )
    other = _create(kb, propose, {"op_type": "create_entity", "kind": "organization", "name": "B"})
    edge = {"op_type": "add_edge", "src": rust, "rel": "related_to", "dst": acme}
    apply.commit_proposal(kb, propose(edge, accept=True))
    again = propose(edge, accept=True)
    assert _operation(kb, again).classification == "known"
    with kb.begin() as conn:
        conn.execute(sa.update(schema.edge).values(dst_id=other))
    with pytest.raises(apply.StaleClassificationError):
        apply.commit_proposal(kb, again)


def test_similarity_runs_outside_any_write_transaction(tmp_path: Path, open_db: OpenDb) -> None:
    engine = open_db(tmp_path / "kb.db")
    source_id = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic chat")
    evidence_id = apply.record_evidence(engine, source_id, "message:1", "I used Go at Acme.")
    touched: list[int] = []

    def similar(kind: EntityKind, name: str) -> int | None:
        # A write from another connection: it would block, then fail, if the
        # proposal's own write lock were already held while we are being asked.
        touched.append(apply.record_source(engine, SourceKind.CONVERSATION, "from the finder"))
        return None

    apply.record_proposal(engine, _input(source_id, evidence_id, GO), similar=similar)
    assert len(touched) == 1


def test_a_differently_named_near_match_is_recorded_as_a_duplicate(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    rust = _create(kb, propose, RUST)
    draft = _input(_source_of(kb, evidence_id), evidence_id, GO)
    proposal = apply.record_proposal(kb, draft, similar=lambda _kind, _name: rust)
    operation = _operation(kb, proposal)
    assert (operation.classification, operation.target_id) == ("duplicate", rust)


def test_a_name_match_wins_over_similarity(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    rust = _create(kb, propose, RUST)
    go = _create(kb, propose, GO)
    draft = _input(_source_of(kb, evidence_id), evidence_id, GO)
    proposal = apply.record_proposal(kb, draft, similar=lambda _kind, _name: rust)
    operation = _operation(kb, proposal)
    assert (operation.classification, operation.target_id) == ("known", go)


def test_a_similar_finder_that_raises_propagates_and_stores_nothing(
    kb: sa.Engine, evidence_id: int
) -> None:
    def broken(_kind: EntityKind, _name: str) -> int | None:
        raise RuntimeError("embedder down")

    with kb.connect() as conn:
        before = queries.table_counts(conn)
    with pytest.raises(RuntimeError, match="embedder down"):
        apply.record_proposal(
            kb, _input(_source_of(kb, evidence_id), evidence_id, GO), similar=broken
        )
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before


def test_a_known_create_entity_pointing_at_an_edge_is_refused(
    kb: sa.Engine, propose: Propose, forge: Forge
) -> None:
    rust = _create(kb, propose, RUST)
    acme = _create(
        kb, propose, {"op_type": "create_entity", "kind": "organization", "name": "Acme"}
    )
    edge = {"op_type": "add_edge", "src": rust, "rel": "related_to", "dst": acme}
    apply.commit_proposal(kb, propose(edge, accept=True))
    with kb.connect() as conn:
        stored = queries.find_edge(conn, rust, "related_to", acme)
    assert stored is not None
    proposal = propose(RUST, accept=True)
    forge(proposal, "known", "edge", stored.id)
    with pytest.raises(apply.StaleClassificationError):
        apply.commit_proposal(kb, proposal)


def test_an_attach_evidence_has_no_statement_to_recheck(
    kb: sa.Engine, propose: Propose, forge: Forge
) -> None:
    rust = _create(kb, propose, RUST)
    attach = {"op_type": "attach_evidence", "target_kind": "entity", "target_id": rust}
    proposal = propose(attach, accept=True)
    forge(proposal, "known", "entity", rust)
    apply.commit_proposal(kb, proposal)  # nothing to contradict, so it applies


def test_the_locked_state_wins_when_the_database_moved_during_similarity(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    created: list[int] = []

    def similar(_kind: EntityKind, _name: str) -> int | None:
        created.append(_create(kb, propose, GO))  # another writer lands while we look
        return None

    draft = _input(_source_of(kb, evidence_id), evidence_id, GO)
    proposal = apply.record_proposal(kb, draft, similar=similar)
    operation = _operation(kb, proposal)
    assert (operation.classification, operation.target_id) == ("known", created[0])
