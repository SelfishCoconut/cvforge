"""Regression tests for the M1a provenance audit (PR #68): defects in `kb/apply.py`.

Each test names the failure it pins. They are grouped here, rather than spread
across the pipeline tests, so the audit's findings stay reviewable as one set.
"""

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.pool import StaticPool

from cvforge.kb import apply, queries
from cvforge.kb.models import ProposalDraft
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind, TargetKind

Propose = Callable[..., int]


def _operations(kb: sa.Engine, proposal: int) -> list[queries.OperationRecord]:
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    return record.operations


# --- an edge conflict must not erase what the payload does not state ---------


def test_an_edge_conflict_changes_only_the_stated_columns_and_records_the_values(
    kb: sa.Engine, propose: Propose
) -> None:
    created = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            {
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "used_in",
                "dst": {"op": 1},
                "confidence": 0.9,
                "started_at": "2020-01-01",
                "ended_at": "2021-01-01",
                "note": "led the rewrite",
            },
            accept=True,
        ),
    )
    rust, parser = created.entity_ids[0], created.entity_ids[1]
    with kb.connect() as conn:
        before = queries.find_edge(conn, rust, "used_in", parser)
    assert before is not None

    contest_start = {
        "op_type": "add_edge",
        "src": rust,
        "rel": "used_in",
        "dst": parser,
        "started_at": "2020-06-01",
    }
    apply.commit_proposal(kb, propose((contest_start, "conflict", "edge", before.id), accept=True))

    with kb.connect() as conn:
        after = queries.find_edge(conn, rust, "used_in", parser)
        history = queries.provenance(conn, TargetKind.EDGE, before.id)
    assert after is not None
    assert str(after.started_at) == "2020-06-01"
    assert (after.confidence, str(after.ended_at), after.note) == (
        0.9,
        "2021-01-01",
        "led the rewrite",
    )
    # The original whole-edge assertion is history; the conflict adds one with the value.
    assert [(a.field, a.value) for a in history] == [(None, None), ("started_at", "2020-06-01")]


# --- an edit must cite evidence that exists ----------------------------------


def test_an_edit_citing_missing_evidence_is_refused_at_review(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"})
    operation = _operations(kb, proposal)[0]
    edited: dict[str, JsonValue] = {
        "op_type": "create_entity",
        "kind": "skill",
        "name": "Rust",
        "evidence_id": 9999,
    }
    with pytest.raises(apply.NotFoundError, match="evidence"):
        apply.review_operation(kb, operation.id, "edit", edited)


@pytest.mark.parametrize(("locator", "excerpt"), [("", "text"), ("message:1", "   "), (" ", " ")])
def test_evidence_with_a_blank_locator_or_excerpt_is_refused(
    kb: sa.Engine, locator: str, excerpt: str
) -> None:
    source = apply.record_source(kb, SourceKind.CONVERSATION, "synthetic")
    with pytest.raises(ValueError, match="non-blank"):
        apply.record_evidence(kb, source, locator, excerpt)


# --- commit relies on foreign keys, so it must check they are on -------------


def test_commit_refuses_an_engine_without_foreign_key_enforcement() -> None:
    engine = sa.create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    try:
        _assert_commit_refused_without_foreign_keys(engine)
    finally:
        engine.dispose()


def _assert_commit_refused_without_foreign_keys(engine: sa.Engine) -> None:
    metadata.create_all(engine)
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "I use Rust.")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "s",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "op_type": "create_entity",
                        "kind": "skill",
                        "name": "Rust",
                        "evidence_id": evidence,
                    },
                    "classification": "new",
                }
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    apply.review_operation(engine, _operations(engine, proposal)[0].id, "accept")
    with pytest.raises(RuntimeError, match="foreign-key"):
        apply.commit_proposal(engine, proposal)
    with engine.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 0


# --- re-deciding replaces the previous decision, including an edit -----------


def test_accepting_after_an_edit_discards_the_edit(kb: sa.Engine, propose: Propose) -> None:
    """Pins today's behaviour (audit F7): each decision replaces the last one.

    A UI must therefore treat an `edited` operation as already approved and offer
    reject or re-edit, not accept.
    """
    proposal = propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"})
    operation = _operations(kb, proposal)[0]
    edited = {**operation.payload, "name": "Rust (lang)"}
    apply.review_operation(kb, operation.id, "edit", edited)
    assert _operations(kb, proposal)[0].status == "edited"

    apply.review_operation(kb, operation.id, "accept")
    after = _operations(kb, proposal)[0]
    assert (after.status, after.edited_payload) == ("accepted", None)
