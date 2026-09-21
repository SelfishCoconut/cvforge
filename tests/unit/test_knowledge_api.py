"""Read-only knowledge endpoints (FR-04 filtering over HTTP)."""

from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import apply

Propose = Callable[..., int]


def _seed(kb: sa.Engine, propose: Propose) -> dict[int, int]:
    return apply.commit_proposal(
        kb,
        propose(
            {
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Rust",
                "attributes": {"category": "language"},
            },
            {"op_type": "create_entity", "kind": "project", "name": "Parser", "state": "learning"},
            {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
            accept=True,
        ),
    ).entity_ids


def test_entities_filter_by_kind_and_state(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    _seed(kb, propose)
    assert [e["name"] for e in client.get("/api/entities?kind=skill").json()] == ["Rust"]
    assert [e["name"] for e in client.get("/api/entities?state=learning").json()] == ["Parser"]
    assert client.get("/api/entities?state=rusty").status_code == 422


def test_one_entity_with_attributes_and_its_edges(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    ids = _seed(kb, propose)
    entity = client.get(f"/api/entities/{ids[0]}").json()
    assert entity["attributes"] == {"category": "language"}
    edges = client.get(f"/api/entities/{ids[0]}/edges").json()
    assert [(e["rel"], e["dst_id"]) for e in edges] == [("used_in", ids[1])]


def test_a_missing_entity_is_404(client: TestClient) -> None:
    assert client.get("/api/entities/404").status_code == 404
