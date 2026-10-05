"""`kb.intake.propose` turns extracted payloads into one stored proposal (FR-07)."""

from collections.abc import Mapping
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter, ValidationError

from cvforge.kb import intake, queries
from cvforge.kb.classify import SimilarFinder
from cvforge.kb.embeddings import EmbeddingError
from cvforge.kb.models import Payload
from cvforge.kb.vocab import EntityKind, Origin

_PAYLOAD: TypeAdapter[Any] = TypeAdapter(Payload)


def _payloads(evidence_id: int, *raw: Mapping[str, Any]) -> list[Payload]:
    return [_PAYLOAD.validate_python({"evidence_id": evidence_id, **item}) for item in raw]


def _source_of(kb: sa.Engine, evidence_id: int) -> int:
    with kb.connect() as conn:
        return int(
            conn.execute(
                sa.text("select source_id from evidence where id = :i"), {"i": evidence_id}
            ).scalar_one()
        )


def _propose(
    kb: sa.Engine, evidence_id: int, *raw: Mapping[str, Any], similar: SimilarFinder | None = None
) -> intake.Intake | None:
    return intake.propose(
        kb,
        origin=Origin.CHAT,
        source_id=_source_of(kb, evidence_id),
        summary="chat message",
        payloads=_payloads(evidence_id, *raw),
        similar=similar,
    )


GO: dict[str, Any] = {"op_type": "create_entity", "kind": "skill", "name": "Go"}
RUST: dict[str, Any] = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def test_an_empty_batch_returns_none_and_touches_nothing(kb: sa.Engine, evidence_id: int) -> None:
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    assert _propose(kb, evidence_id) is None
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before


def test_two_payloads_become_one_proposal_in_order(kb: sa.Engine, evidence_id: int) -> None:
    stored = _propose(kb, evidence_id, GO, RUST)
    assert stored is not None
    with kb.connect() as conn:
        record = queries.get_proposal(conn, stored.proposal_id)
    assert record is not None
    assert [op.seq for op in record.operations] == [0, 1]
    assert [op.classification for op in record.operations] == ["new", "new"]
    assert stored.similarity_available is True


def test_a_reference_to_an_earlier_create_is_stored_new(kb: sa.Engine, evidence_id: int) -> None:
    edge = {
        "op_type": "add_edge",
        "src": {"op": 0},
        "rel": "used_in",
        "dst": {"op": 1},
    }
    project = {"op_type": "create_entity", "kind": "project", "name": "Parser"}
    stored = _propose(kb, evidence_id, GO, project, edge)
    assert stored is not None
    with kb.connect() as conn:
        record = queries.get_proposal(conn, stored.proposal_id)
    assert record is not None
    assert record.operations[2].classification == "new"


def test_an_unresolvable_reference_raises_and_stores_nothing(
    kb: sa.Engine, evidence_id: int
) -> None:
    edge = {"op_type": "add_edge", "src": {"op": 5}, "rel": "used_in", "dst": {"op": 0}}
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    with pytest.raises(ValidationError):
        _propose(kb, evidence_id, GO, edge)
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before


def test_an_embedding_failure_still_stores_the_proposal_and_says_so(
    kb: sa.Engine, evidence_id: int
) -> None:
    def down(kind: EntityKind, name: str) -> int | None:
        raise EmbeddingError("endpoint is down")

    stored = _propose(kb, evidence_id, GO, similar=down)
    assert stored is not None
    assert stored.similarity_available is False
    with kb.connect() as conn:
        assert queries.get_proposal(conn, stored.proposal_id) is not None


def test_a_working_similarity_is_reported_available(kb: sa.Engine, evidence_id: int) -> None:
    calls: list[str] = []

    def finder(kind: EntityKind, name: str) -> int | None:
        calls.append(name)
        return None

    stored = _propose(kb, evidence_id, GO, similar=finder)
    assert stored is not None and stored.similarity_available is True
    assert calls == ["Go"]


def test_a_failure_other_than_embedding_still_propagates(kb: sa.Engine, evidence_id: int) -> None:
    def broken(kind: EntityKind, name: str) -> int | None:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        _propose(kb, evidence_id, GO, similar=broken)
    with kb.connect() as conn:
        assert queries.table_counts(conn)["proposal"] == 0
