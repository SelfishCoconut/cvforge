"""Read-query behaviours that were untested even at 100% line coverage.

Each test is built so the specific mistake it guards against would change the
answer: entity #1 and edge #1 deliberately share an id, and the graph has one edge
seen from both of its ends.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply, queries, schema
from cvforge.kb.vocab import EntityKind, KnowledgeState, TargetKind

Propose = Callable[..., int]


def _graph(kb: sa.Engine, propose: Propose) -> tuple[int, int]:
    """Rust (skill, id 1) used_in Parser (project, id 2): edge id 1, entity id 1 too."""
    result = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
            accept=True,
        ),
    )
    return result.entity_ids[0], result.entity_ids[1]


def test_an_edge_is_found_from_both_of_its_ends(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    rust, parser = _graph(kb, propose)
    for entity in (rust, parser):
        edges = client.get(f"/api/entities/{entity}/edges").json()
        assert [(e["src_id"], e["dst_id"]) for e in edges] == [(rust, parser)]


def test_provenance_is_scoped_to_the_target_kind(kb: sa.Engine, propose: Propose) -> None:
    rust, _ = _graph(kb, propose)
    with kb.connect() as conn:
        edge = queries.find_edge(conn, rust, "used_in", _)
        assert edge is not None
        assert edge.id == rust  # the ids collide on purpose: entity 1 and edge 1
        entity_history = queries.provenance(conn, TargetKind.ENTITY, rust)
        edge_history = queries.provenance(conn, TargetKind.EDGE, edge.id)
    assert len(edge_history) == 1  # only the edge's own assertion
    assert len(entity_history) >= 3  # the entity's whole-fact, name and state assertions


def test_entities_filter_on_kind_and_state_together(kb: sa.Engine, propose: Propose) -> None:
    _graph(kb, propose)
    with kb.connect() as conn:
        assert (
            queries.list_entities(conn, kind=EntityKind.SKILL, state=KnowledgeState.LEARNING) == []
        )
        confirmed_skills = queries.list_entities(
            conn, kind=EntityKind.SKILL, state=KnowledgeState.CONFIRMED
        )
    assert [e.name for e in confirmed_skills] == ["Rust"]


def test_the_orphan_report_sees_an_assertion_about_an_edge_that_does_not_exist(
    kb: sa.Engine, evidence_id: int
) -> None:
    with kb.begin() as conn:
        conn.execute(
            sa.insert(schema.assertion).values(
                target_kind="edge",
                target_id=999,
                field=None,
                value_json=None,
                evidence_id=evidence_id,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
    with kb.connect() as conn:
        report = queries.orphans(conn)
    assert report.assertions_without_target != []
    assert not report.clean
