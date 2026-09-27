"""FR-10: a proposal commits atomically, on a real migrated database file."""

from collections.abc import Callable
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


def _propose(engine: sa.Engine, payloads: list[dict[str, object]]) -> int:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "synthetic statement")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "synthetic",
            "operations": [
                {"seq": i, "payload": {"evidence_id": evidence, **p}, "classification": "new"}
                for i, p in enumerate(payloads)
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    for op in record.operations:
        apply.review_operation(engine, op.id, "accept")
    return proposal


def _counts(engine: sa.Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return queries.table_counts(conn)


def test_n_accepted_operations_are_written_together_with_a_commit_log(db: sa.Engine) -> None:
    proposal = _propose(
        db,
        [
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
        ],
    )
    result = apply.commit_proposal(db, proposal)
    with db.connect() as conn:
        log = conn.execute(sa.select(schema.commit_log)).one()
        report = queries.orphans(conn)
        record = queries.get_proposal(conn, proposal)
    assert _counts(db)["entity"] == 2 and _counts(db)["edge"] == 1
    assert log.operation_ids_json == result.applied_operation_ids
    assert record is not None and log.operation_ids_json == [op.id for op in record.operations]
    assert report.clean


def test_a_failure_on_the_last_operation_rolls_everything_back(db: sa.Engine) -> None:
    rust = apply.commit_proposal(
        db, _propose(db, [{"op_type": "create_entity", "kind": "skill", "name": "Rust"}])
    ).entity_ids[0]
    before = _counts(db)
    proposal = _propose(
        db,
        [
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            {"op_type": "add_edge", "src": rust, "rel": "used_in", "dst": {"op": 0}},
            # the same triple again: the UNIQUE constraint fails on the LAST operation
            {"op_type": "add_edge", "src": rust, "rel": "used_in", "dst": {"op": 0}},
        ],
    )
    after_proposing = _counts(db)
    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE"):
        apply.commit_proposal(db, proposal)
    assert _counts(db) == after_proposing
    assert {k: after_proposing[k] for k in ("entity", "edge", "assertion")} == {
        k: before[k] for k in ("entity", "edge", "assertion")
    }
    with db.connect() as conn:
        record = queries.get_proposal(conn, proposal)
        logs = conn.execute(sa.select(sa.func.count()).select_from(schema.commit_log)).scalar_one()
    assert record is not None and record.status == "open"
    assert {op.status for op in record.operations} == {"accepted"}
    assert logs == 1  # only the first, successful commit


def test_a_committed_database_survives_reopening(
    db: sa.Engine, tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    apply.commit_proposal(
        db, _propose(db, [{"op_type": "create_entity", "kind": "skill", "name": "Rust"}])
    )
    db.dispose()
    reopened = open_db(tmp_path / "cvforge.db")
    with reopened.connect() as conn:
        assert [e.name for e in queries.list_entities(conn)] == ["Rust"]
