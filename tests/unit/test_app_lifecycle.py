"""The app's lifespan owns only what it opened."""

from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.kb import apply, queries

Propose = Callable[..., int]


def test_the_app_does_not_dispose_an_engine_it_was_given(kb: sa.Engine, propose: Propose) -> None:
    """`create_app(engine=...)` documents that the caller keeps ownership.

    The in-memory `kb` sits on a single shared connection, so disposing it would
    silently discard every row: reading them back after the app has shut down proves
    the engine was left alone.
    """
    apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True)
    )

    with TestClient(create_app(engine=kb)) as client:
        assert client.get("/api/entities").status_code == 200

    with kb.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 1
