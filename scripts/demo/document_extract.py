"""Demo (FR-15, M2): upload a document, extract cited facts, review and commit them.

Offline and in memory: the model is a scripted stand-in, so no Ollama and no network.
It exits non-zero if extraction wrote any knowledge before review, if a locator does not
reproduce its excerpt, or if a fabricated quote was proposed.
"""

import re
import tempfile
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import queries, schema
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata

TEXT = "# Experience\n\nBuilt a log parser in Rust that processes two gigabytes per second.\n"
SCRIPTED = {
    "facts": [
        {"local_id": "s", "kind": "skill", "name": "Rust", "excerpt": "Built a log parser in Rust"},
        {
            "local_id": "k",
            "kind": "skill",
            "name": "Kubernetes",
            "excerpt": "ran clusters at Globex",
        },
    ],
    "edges": [],
}


def _locators_reproduce(engine: sa.Engine, text: str) -> bool:
    with engine.connect() as conn:
        rows = conn.execute(sa.select(schema.evidence.c.locator, schema.evidence.c.excerpt)).all()
    for locator, excerpt in rows:
        match = re.fullmatch(r"page:1 chars:(\d+)-(\d+)", locator)
        if match is None or text[int(match[1]) : int(match[2])] != excerpt:
            return False
    return bool(rows)


def main() -> int:
    """Upload a Markdown file, extract, show the proposal, review and commit it.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine)
        app.state.model_factory = lambda _engine: TestModel(custom_output_args=SCRIPTED)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            up = client.post("/api/documents", files={"file": ("cv.md", TEXT.encode())}).json()
            print(f"1. uploaded  cv.md -> source {up['source_id']}")
            body = client.post(f"/api/documents/{up['source_id']}/extract").json()
            proposal = body["proposal"]
            for op in proposal["operations"]:
                print(f"2. proposed  #{op['seq']} {op['op_type']} ({op['classification']})")
            for item in body["rejected"]:
                print(f"3. dropped   {item['item']}: {item['reason']}")
            with engine.connect() as conn:
                before = queries.table_counts(conn)
            if before["entity"] or before["edge"] or before["assertion"]:
                print("FAIL: knowledge written before review")
                return 1
            for op in proposal["operations"]:
                url = f"/api/proposals/{proposal['id']}/operations/{op['id']}/review"
                client.post(url, json={"decision": "accept"}).raise_for_status()
            client.post(f"/api/proposals/{proposal['id']}/commit").raise_for_status()
    with engine.connect() as conn:
        after = queries.table_counts(conn)
    ok = _locators_reproduce(engine, TEXT)
    print(f"4. committed entities={after['entity']}; locators reproduce excerpts: {ok}")
    return 0 if after["entity"] == 1 and ok and len(body["rejected"]) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
