"""Invariant 3, path by path: every accepted operation asserts what it did, with its evidence.

`test_every_write_path_leaves_zero_orphans` proves the orphan report stays clean.
That cannot catch a path that writes *no* assertion, because every entity and edge
already carries the assertion from its creation. These tests count assertions and
read each one's field, value and cited excerpt.
"""

from collections.abc import Callable

import sqlalchemy as sa

from cvforge.kb import apply, queries
from cvforge.kb.vocab import SourceKind, TargetKind

Propose = Callable[..., int]

SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def _facts(kb: sa.Engine, kind: TargetKind, target_id: int) -> list[tuple[str | None, object]]:
    with kb.connect() as conn:
        return [(p.field, p.value) for p in queries.provenance(conn, kind, target_id)]


def _assertions(kb: sa.Engine) -> int:
    with kb.connect() as conn:
        return queries.table_counts(conn)["assertion"]


def test_each_stated_attribute_of_a_created_entity_is_asserted_with_its_value(
    kb: sa.Engine, propose: Propose
) -> None:
    create = {
        "op_type": "create_entity",
        "kind": "project",
        "name": "Parser",
        "summary": "a log parser",
        "attributes": {"started_at": "2021-01-01", "context": "internal", "ended_at": None},
    }
    entity = apply.commit_proposal(kb, propose(create, accept=True)).entity_ids[0]

    facts = _facts(kb, TargetKind.ENTITY, entity)
    fields = {field for field, _ in facts}
    assert ("started_at", "2021-01-01") in facts
    assert ("context", "internal") in facts
    assert ("summary", "a log parser") in facts
    assert {None, "name", "state"} <= fields
    assert "ended_at" not in fields  # an attribute left unstated is not asserted


def test_a_kind_attribute_update_asserts_the_field_and_its_value(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = apply.commit_proposal(kb, propose(SKILL, accept=True)).entity_ids[0]
    before = _assertions(kb)

    update = {
        "op_type": "update_field",
        "entity_id": rust,
        "field": "category",
        "value": "language",
    }
    apply.commit_proposal(kb, propose(update, accept=True))

    assert _assertions(kb) == before + 1
    assert _facts(kb, TargetKind.ENTITY, rust)[-1] == ("category", "language")


def test_a_known_update_asserts_the_field_and_the_value_it_confirms(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = apply.commit_proposal(kb, propose({**SKILL, "summary": "systems"}, accept=True))
    rust_id = rust.entity_ids[0]
    same = {"op_type": "update_field", "entity_id": rust_id, "field": "summary", "value": "Systems"}

    apply.commit_proposal(kb, propose((same, "known", "entity", rust_id), accept=True))

    assert _facts(kb, TargetKind.ENTITY, rust_id)[-1] == ("summary", "Systems")


def test_attaching_evidence_keeps_the_field_it_supports(kb: sa.Engine, propose: Propose) -> None:
    rust = apply.commit_proposal(kb, propose(SKILL, accept=True)).entity_ids[0]
    before = _assertions(kb)

    attach = {
        "op_type": "attach_evidence",
        "target_kind": "entity",
        "target_id": rust,
        "field": "name",
    }
    apply.commit_proposal(kb, propose((attach, "known", "entity", rust), accept=True))

    assert _assertions(kb) == before + 1
    assert _facts(kb, TargetKind.ENTITY, rust)[-1] == ("name", None)


def test_every_assertion_cites_the_evidence_of_its_own_operation(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    """Two operations, two different messages: neither may cite the other's."""
    source = apply.record_source(kb, SourceKind.CONVERSATION, "second synthetic chat")
    second = apply.record_evidence(kb, source, "message:1", "I also use Go.")

    created = apply.commit_proposal(
        kb,
        propose(
            SKILL,
            {"op_type": "create_entity", "kind": "skill", "name": "Go", "evidence_id": second},
            accept=True,
        ),
    )

    with kb.connect() as conn:
        rust = queries.provenance(conn, TargetKind.ENTITY, created.entity_ids[0])
        go = queries.provenance(conn, TargetKind.ENTITY, created.entity_ids[1])
    assert {p.excerpt for p in rust} == {"I built a parser in Rust at Acme."}
    assert {p.excerpt for p in go} == {"I also use Go."}
    assert evidence_id != second
