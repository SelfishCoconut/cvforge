"""An edge between entities that are already known is itself known or in conflict (FR-16).

Restating a fact and the edge that joins it to another used to classify the edge `new`,
because its endpoints were references to operations in the same proposal; committing it
then violated the edge's unique key and refused the whole proposal.
"""

from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa

from cvforge.kb import apply, queries

Propose = Callable[..., int]

RUST = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}
PARSER = {"op_type": "create_entity", "kind": "project", "name": "Parser"}
EDGE = {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}}


@pytest.fixture
def stored(kb: sa.Engine, propose: Propose) -> None:
    apply.commit_proposal(
        kb, propose(RUST, PARSER, {**EDGE, "started_at": "2021-01-01"}, accept=True)
    )


def _classes(kb: sa.Engine, proposal_id: int) -> list[tuple[str, str | None]]:
    with kb.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    assert record is not None
    return [(op.classification, op.target_kind) for op in record.operations]


def _counts(kb: sa.Engine) -> dict[str, int]:
    with kb.connect() as conn:
        return queries.table_counts(conn)


@pytest.mark.usefixtures("stored")
def test_restating_a_whole_graph_classifies_every_operation_known(
    kb: sa.Engine, propose: Propose
) -> None:
    again = propose(RUST, PARSER, {**EDGE, "started_at": "2021-01-01"})

    assert _classes(kb, again) == [("known", "entity"), ("known", "entity"), ("known", "edge")]


@pytest.mark.usefixtures("stored")
def test_committing_a_restated_graph_adds_evidence_and_creates_nothing(
    kb: sa.Engine, propose: Propose
) -> None:
    before = _counts(kb)

    apply.commit_proposal(
        kb, propose(RUST, PARSER, {**EDGE, "started_at": "2021-01-01"}, accept=True)
    )

    after = _counts(kb)
    assert (after["entity"], after["edge"]) == (before["entity"], before["edge"])
    assert after["assertion"] == before["assertion"] + 3


@pytest.mark.usefixtures("stored")
def test_a_restated_edge_with_different_dates_is_a_conflict(
    kb: sa.Engine, propose: Propose
) -> None:
    again = propose(RUST, PARSER, {**EDGE, "started_at": "2019-01-01"})

    assert _classes(kb, again)[2] == ("conflict", "edge")


@pytest.mark.usefixtures("stored")
def test_an_edge_to_a_new_entity_stays_new(kb: sa.Engine, propose: Propose) -> None:
    haskell: dict[str, Any] = {"op_type": "create_entity", "kind": "project", "name": "Compiler"}

    again = propose(RUST, haskell, EDGE)

    assert _classes(kb, again) == [("known", "entity"), ("new", None), ("new", None)]
    # a half-known edge must still commit cleanly
    apply.commit_proposal(kb, propose(RUST, haskell, EDGE, accept=True))


def test_on_an_empty_knowledge_base_nothing_is_known(kb: sa.Engine, propose: Propose) -> None:
    assert _classes(kb, propose(RUST, PARSER, EDGE)) == [("new", None)] * 3
