"""NFR-02 and audit F6: the Host and Origin checks `api/security.py` adds.

Both run as in-process ASGI middleware over `TestClient`, no real socket — the
one check that needs a genuine non-loopback connection attempt is
`tests/integration/test_app_bind.py`.
"""

import re
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb import queries

Propose = Callable[..., int]
SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def test_the_route_inventory_has_no_auth_endpoints(client: TestClient) -> None:
    """NFR-02: single-user local tool, no login/session/token endpoint (design spec §3)."""
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if re.search(r"login|logout|session|token|auth", p)]


def test_a_foreign_host_header_is_refused(client: TestClient) -> None:
    """DNS rebinding: a page on attacker.example resolved to 127.0.0.1 still sends that Host."""
    response = client.get("/api/health", headers={"Host": "attacker.example"})
    assert response.status_code == 400


def test_the_apps_own_host_forms_are_all_accepted(client: TestClient) -> None:
    for host in ("127.0.0.1", "localhost", "[::1]"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_an_unsafe_request_from_a_foreign_origin_is_refused_and_changes_nothing(
    client: TestClient, kb: sa.Engine, propose: Propose
) -> None:
    proposal = propose(SKILL, accept=True)
    response = client.post(
        f"/api/proposals/{proposal}/commit", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    with kb.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 0


def test_a_same_origin_unsafe_request_still_works(client: TestClient, propose: Propose) -> None:
    proposal = propose(SKILL, accept=True)
    response = client.post(
        f"/api/proposals/{proposal}/commit", headers={"Origin": "http://127.0.0.1:8000"}
    )
    assert response.status_code == 200  # a different port is still this machine


def test_safe_methods_ignore_origin(client: TestClient) -> None:
    """A GET carries no side effect here, so a foreign Origin does not block it."""
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200


def test_a_request_with_no_origin_header_at_all_is_not_blocked(
    client: TestClient, propose: Propose
) -> None:
    """Most real requests to this API carry no Origin at all (curl, the SPA's own fetches)."""
    proposal = propose(SKILL, accept=True)
    response = client.post(f"/api/proposals/{proposal}/commit")
    assert response.status_code == 200
