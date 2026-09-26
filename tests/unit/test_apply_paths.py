"""The commit path's less obvious branches: renames, attributes, refusals, references."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa

from cvforge.kb import apply, export, migrate, queries
from cvforge.kb.db import make_engine
from cvforge.kb.vocab import TargetKind

Propose = Callable[..., int]


@pytest.fixture
def rust(kb: sa.Engine, propose: Propose) -> int:
    result = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True)
    )
    return result.entity_ids[0]


def _counts(kb: sa.Engine) -> dict[str, int]:
    with kb.connect() as conn:
        return queries.table_counts(conn)


def test_renaming_recomputes_the_normalized_name(
    kb: sa.Engine, propose: Propose, rust: int
) -> None:
    update = {"op_type": "update_field", "entity_id": rust, "field": "name", "value": "Rust  Lang"}
    apply.commit_proposal(kb, propose(update, accept=True))
    with kb.connect() as conn:
        entity = queries.get_entity(conn, rust)
    assert entity is not None
    assert (entity.name, entity.normalized_name) == ("Rust  Lang", "rust lang")


@pytest.mark.parametrize("value", ["   ", 7])
def test_a_blank_or_non_text_name_is_refused(
    kb: sa.Engine, propose: Propose, rust: int, value: object
) -> None:
    update = {"op_type": "update_field", "entity_id": rust, "field": "name", "value": value}
    with pytest.raises(apply.InvalidEditError, match="name"):
        apply.commit_proposal(kb, propose(update, accept=True))


def test_a_kind_attribute_is_updated_typed(kb: sa.Engine, propose: Propose, rust: int) -> None:
    update = {
        "op_type": "update_field",
        "entity_id": rust,
        "field": "category",
        "value": "language",
    }
    apply.commit_proposal(kb, propose(update, accept=True))
    with kb.connect() as conn:
        entity = queries.get_entity(conn, rust)
    assert entity is not None and entity.attributes["category"] == "language"


def test_an_attribute_the_kind_does_not_have_is_refused(
    kb: sa.Engine, propose: Propose, rust: int
) -> None:
    update = {"op_type": "update_field", "entity_id": rust, "field": "degree", "value": "BSc"}
    with pytest.raises(apply.InvalidEditError, match="no field 'degree'"):
        apply.commit_proposal(kb, propose(update, accept=True))


def test_updating_a_missing_entity_is_not_found(kb: sa.Engine, propose: Propose) -> None:
    update = {"op_type": "update_field", "entity_id": 99, "field": "summary", "value": "x"}
    with pytest.raises(apply.NotFoundError, match="entity 99"):
        apply.commit_proposal(kb, propose(update, accept=True))


def test_an_edge_to_a_rejected_creation_rolls_the_whole_proposal_back(
    kb: sa.Engine, propose: Propose, rust: int
) -> None:
    proposal = propose(
        {"op_type": "create_entity", "kind": "project", "name": "Parser"},
        {"op_type": "add_edge", "src": rust, "rel": "used_in", "dst": {"op": 0}},
        {"op_type": "create_entity", "kind": "skill", "name": "Go"},
    )
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    create, edge, other = record.operations
    apply.review_operation(kb, create.id, "reject")
    apply.review_operation(kb, edge.id, "accept")
    apply.review_operation(kb, other.id, "accept")
    before = _counts(kb)
    with pytest.raises(apply.UnsupportedOperationError, match="was not applied"):
        apply.commit_proposal(kb, proposal)
    assert _counts(kb) == before  # Go was not kept either: atomic


def test_attach_evidence_adds_an_assertion_to_an_existing_target(
    kb: sa.Engine, propose: Propose, rust: int
) -> None:
    attach = {"op_type": "attach_evidence", "target_kind": "entity", "target_id": rust}
    apply.commit_proposal(kb, propose(attach, accept=True))
    with kb.connect() as conn:
        supports = [p for p in queries.provenance(conn, TargetKind.ENTITY, rust) if p.field is None]
    assert len(supports) == 2


def test_attach_evidence_to_a_missing_target_is_not_found(kb: sa.Engine, propose: Propose) -> None:
    attach = {"op_type": "attach_evidence", "target_kind": "edge", "target_id": 5}
    with pytest.raises(apply.NotFoundError, match="edge 5"):
        apply.commit_proposal(kb, propose(attach, accept=True))


@pytest.mark.parametrize(
    ("payload", "field", "value"),
    [
        ({"op_type": "set_state", "state": "confirmed"}, "state", "confirmed"),
        ({"op_type": "attach_evidence", "target_kind": "entity", "field": "name"}, "name", None),
    ],
)
def test_known_operations_add_a_field_level_assertion(
    kb: sa.Engine,
    propose: Propose,
    rust: int,
    payload: dict[str, object],
    field: str,
    value: object,
) -> None:
    body = (
        {**payload, "entity": rust}
        if payload["op_type"] == "set_state"
        else {**payload, "target_id": rust}
    )
    apply.commit_proposal(kb, propose((body, "known", "entity", rust), accept=True))
    with kb.connect() as conn:
        last = queries.provenance(conn, TargetKind.ENTITY, rust)[-1]
    assert (last.field, last.value) == (field, value)


def test_a_known_operation_whose_target_vanished_is_not_found(
    kb: sa.Engine, propose: Propose
) -> None:
    known = ({"op_type": "create_entity", "kind": "skill", "name": "Go"}, "known", "entity", 77)
    with pytest.raises(apply.NotFoundError, match="entity 77"):
        apply.commit_proposal(kb, propose(known, accept=True))


def test_a_create_entity_cannot_be_applied_as_a_conflict(
    kb: sa.Engine, propose: Propose, rust: int
) -> None:
    conflict = (
        {"op_type": "create_entity", "kind": "skill", "name": "Go"},
        "conflict",
        "entity",
        rust,
    )
    with pytest.raises(apply.UnsupportedOperationError, match="conflict"):
        apply.commit_proposal(kb, propose(conflict, accept=True))


def test_set_state_on_a_missing_entity_is_not_found(kb: sa.Engine, propose: Propose) -> None:
    with pytest.raises(apply.NotFoundError):
        apply.commit_proposal(
            kb, propose({"op_type": "set_state", "entity": 50, "state": "gap"}, accept=True)
        )


def test_a_proposal_with_every_operation_rejected_commits_nothing(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose({"op_type": "create_entity", "kind": "skill", "name": "Go"})
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    apply.review_operation(kb, record.operations[0].id, "reject")
    result = apply.commit_proposal(kb, proposal)
    assert result.applied_operation_ids == []
    assert _counts(kb)["entity"] == 0


# --- migration and export helpers that need no file --------------------------------


def test_migrating_an_in_memory_database_reaches_head_without_a_backup() -> None:
    engine = make_engine(None)
    try:
        assert migrate.upgrade(engine, Path("unused.db"), Path("unused-backups")) is None
        assert migrate.current_revision(engine) == migrate.head_revision()
    finally:
        engine.dispose()


def test_exporting_a_missing_database_is_refused() -> None:
    with pytest.raises(FileNotFoundError):
        export.export_database(Path("/nonexistent/cvforge.db"), Path("/nonexistent/copy.db"))
