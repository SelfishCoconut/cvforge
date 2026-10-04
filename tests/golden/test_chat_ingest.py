"""Recorded chat messages replayed through the real pipeline, pinned to snapshots (FR-11).

Each fixture holds a synthetic message and the scripted model output. Everything
after the model — the handler, the converter, intake and classification — is real.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.kb import queries

pytestmark = pytest.mark.golden

FIXTURES = Path(__file__).parent / "fixtures" / "chat"
NAMES = sorted(path.stem for path in FIXTURES.glob("*.json"))


@pytest.mark.parametrize("name", NAMES)
def test_replay_matches_snapshot(
    name: str, client: TestClient, kb: sa.Engine, golden: Callable[[str, object], None]
) -> None:
    recorded = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    client.app.state.model_factory = lambda _engine: TestModel(  # type: ignore[attr-defined]
        custom_output_args=recorded["model_output"]
    )

    response = client.post("/api/chat/messages", json={"text": recorded["text"]})

    with kb.connect() as conn:
        counts = queries.table_counts(conn)
    # Nothing in any replay may reach the knowledge itself: review comes first (invariant 4).
    assert (counts["entity"], counts["edge"], counts["assertion"]) == (0, 0, 0)
    golden(
        f"chat/{name}", {"status": response.status_code, "body": response.json(), "counts": counts}
    )
