"""Recorded documents replayed through upload and extraction, pinned to snapshots (FR-15).

Each fixture holds a synthetic document and the scripted model output. Everything
after the model — chunking, locator resolution, conversion, intake and
classification — is real.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.kb import queries, schema

pytestmark = pytest.mark.golden

FIXTURES = Path(__file__).parent / "fixtures" / "document"
NAMES = sorted(path.stem for path in FIXTURES.glob("*.json"))


@pytest.mark.parametrize("name", NAMES)
def test_replay_matches_snapshot(
    name: str,
    client: TestClient,
    kb: sa.Engine,
    tmp_path: Path,
    golden: Callable[[str, object], None],
) -> None:
    recorded = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    client.app.state.settings.data_dir = tmp_path / "data"  # type: ignore[attr-defined]
    client.app.state.model_factory = lambda _engine: TestModel(  # type: ignore[attr-defined]
        custom_output_args=recorded["model_output"]
    )
    upload = client.post(
        "/api/documents", files={"file": (recorded["filename"], recorded["text"].encode())}
    )

    response = client.post(f"/api/documents/{upload.json()['source_id']}/extract")

    with kb.connect() as conn:
        counts = queries.table_counts(conn)
        cited = [
            {"locator": r.locator, "excerpt": r.excerpt}
            for r in conn.execute(
                sa.select(schema.evidence.c.locator, schema.evidence.c.excerpt).order_by(
                    schema.evidence.c.id
                )
            )
        ]
    # Nothing in any replay may reach the knowledge itself: review comes first (invariant 4).
    assert (counts["entity"], counts["edge"], counts["assertion"]) == (0, 0, 0)
    golden(
        f"document/{name}",
        {"status": response.status_code, "body": response.json(), "evidence": cited},
    )
