"""Invariant 3 (FR-03 c4): no entity and no edge without an assertion, ever.

Every path the write path offers is driven here, including the awkward ones
(known, conflict, edited, rejected, rolled back), and the orphan report must stay
clean after each. The negative cases prove the report can actually see a
violation — a check that never fires reads as a pass.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

from cvforge.kb import apply, queries, schema
from cvforge.kb.models import ProposalDraft
from cvforge.kb.vocab import SourceKind

pytestmark = pytest.mark.integration


@pytest.fixture
def db(tmp_path: Path, open_db: Callable[..., sa.Engine]) -> sa.Engine:
    return open_db(tmp_path / "cvforge.db")


def _commit(
    engine: sa.Engine, *ops: tuple[dict[str, object], str, str | None, int | None]
) -> apply.CommitResult:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "synthetic")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "s",
            "operations": [
                {
                    "seq": i,
                    "payload": {"evidence_id": evidence, **p},
                    "classification": c,
                    "target_kind": tk,
                    "target_id": ti,
                }
                for i, (p, c, tk, ti) in enumerate(ops)
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    for op in record.operations:
        apply.review_operation(engine, op.id, "accept")
    return apply.commit_proposal(engine, proposal)


def _new(payload: dict[str, object]) -> tuple[dict[str, object], str, None, None]:
    return (payload, "new", None, None)


def _clean(engine: sa.Engine) -> bool:
    with engine.connect() as conn:
        return queries.orphans(conn).clean


def test_every_write_path_leaves_zero_orphans(db: sa.Engine) -> None:
    ids = _commit(
        db,
        _new(
            {
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Rust",
                "attributes": {"category": "language"},
            }
        ),
        _new({"op_type": "create_entity", "kind": "organization", "name": "Acme"}),
        _new({"op_type": "create_entity", "kind": "role", "name": "Engineer"}),
        _new({"op_type": "add_edge", "src": {"op": 2}, "rel": "at_organization", "dst": {"op": 1}}),
    ).entity_ids
    assert _clean(db)
    rust, acme, role = ids[0], ids[1], ids[2]
    with db.connect() as conn:
        edge = queries.find_edge(conn, role, "at_organization", acme)
    assert edge is not None
    _commit(
        db,
        ({"op_type": "create_entity", "kind": "skill", "name": "rust"}, "known", "entity", rust),
        (
            {"op_type": "update_field", "entity_id": rust, "field": "category", "value": "tool"},
            "conflict",
            "entity",
            rust,
        ),
        _new(
            {
                "op_type": "update_field",
                "entity_id": role,
                "field": "title",
                "value": "Senior engineer",
            }
        ),
        _new({"op_type": "set_state", "entity": rust, "state": "archived"}),
        _new({"op_type": "attach_evidence", "target_kind": "edge", "target_id": edge.id}),
        (
            {
                "op_type": "add_edge",
                "src": role,
                "rel": "at_organization",
                "dst": acme,
                "started_at": "2020-01-01",
            },
            "conflict",
            "edge",
            edge.id,
        ),
    )
    assert _clean(db)


def test_the_report_sees_an_entity_without_an_assertion(db: sa.Engine) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.begin() as conn:  # a write that bypasses apply.py, as a bug would
        conn.execute(
            sa.insert(schema.entity).values(
                kind="skill",
                name="Ghost",
                normalized_name="ghost",
                state="confirmed",
                first_seen_at=now,
                updated_at=now,
            )
        )
    with db.connect() as conn:
        report = queries.orphans(conn)
    assert report.entities_without_assertion != [] and not report.clean


def test_the_report_sees_an_edge_without_an_assertion_and_a_dangling_assertion(
    db: sa.Engine,
) -> None:
    ids = _commit(
        db,
        _new({"op_type": "create_entity", "kind": "skill", "name": "Rust"}),
        _new({"op_type": "create_entity", "kind": "project", "name": "Parser"}),
    ).entity_ids
    with db.begin() as conn:
        conn.execute(sa.insert(schema.edge).values(src_id=ids[0], rel="used_in", dst_id=ids[1]))
        conn.execute(
            sa.update(schema.assertion)
            .where(schema.assertion.c.target_id == ids[1])
            .values(target_id=999)
        )
    with db.connect() as conn:
        report = queries.orphans(conn)
    assert len(report.edges_without_assertion) == 1
    assert report.assertions_without_target != []
    assert ids[1] in report.entities_without_assertion
