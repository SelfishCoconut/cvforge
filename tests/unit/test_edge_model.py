"""FR-02: typed, time-bounded, unique relationships."""

from collections.abc import Callable
from datetime import date

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from cvforge.kb import apply, queries
from cvforge.kb.models import AddEdge

Propose = Callable[..., int]


def _two_entities(kb: sa.Engine, propose: Propose) -> tuple[int, int]:
    result = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            accept=True,
        ),
    )
    return result.entity_ids[0], result.entity_ids[1]


def test_edge_round_trips_with_all_fields(kb: sa.Engine, propose: Propose) -> None:
    rust, parser = _two_entities(kb, propose)
    edge = {
        "op_type": "add_edge",
        "src": rust,
        "rel": "used_in",
        "dst": parser,
        "confidence": 0.9,
        "started_at": "2021-01-01",
        "ended_at": "2021-12-31",
        "note": "core",
    }
    apply.commit_proposal(kb, propose(edge, accept=True))
    with kb.connect() as conn:
        stored = queries.find_edge(conn, rust, "used_in", parser)
    assert stored is not None
    assert (stored.confidence, stored.started_at, stored.ended_at, stored.note) == (
        0.9,
        date(2021, 1, 1),
        date(2021, 12, 31),
        "core",
    )


def test_rel_outside_the_vocabulary_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AddEdge.model_validate({"src": 1, "rel": "loves", "dst": 2, "evidence_id": 1})


def test_duplicate_triple_violates_the_unique_constraint(kb: sa.Engine, propose: Propose) -> None:
    rust, parser = _two_entities(kb, propose)
    edge = {"op_type": "add_edge", "src": rust, "rel": "used_in", "dst": parser}
    apply.commit_proposal(kb, propose(edge, accept=True))
    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE"):
        apply.commit_proposal(kb, propose(edge, accept=True))


def test_inverted_dates_are_rejected() -> None:
    with pytest.raises(ValidationError, match="earlier"):
        AddEdge.model_validate(
            {
                "src": 1,
                "rel": "used_in",
                "dst": 2,
                "started_at": "2022-01-01",
                "ended_at": "2021-01-01",
                "evidence_id": 1,
            }
        )


def test_self_loop_is_rejected() -> None:
    with pytest.raises(ValidationError, match="itself"):
        AddEdge.model_validate({"src": 3, "rel": "related_to", "dst": 3, "evidence_id": 1})


def test_edge_to_an_entity_created_in_the_same_proposal(kb: sa.Engine, propose: Propose) -> None:
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
        edges = queries.neighbours(conn, result.entity_ids[0])
    assert [(e.rel, e.dst_id) for e in edges] == [("at_organization", result.entity_ids[1])]
