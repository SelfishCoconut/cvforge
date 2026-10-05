"""Demo (FR-11, FR-12, M1b): a chat statement becomes a pending proposal, then is committed.

Offline and in memory: the model is a scripted stand-in, so no Ollama and no network.
It exits non-zero if the message wrote anything to the knowledge before review.
"""

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.app import create_app
from cvforge.kb import queries
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata

STATEMENT = "I built a log parser in Rust."
SCRIPTED = {
    "reply": "Noted: a log parser, built with Rust.",
    "facts": [
        {"local_id": "s", "kind": "skill", "name": "Rust", "attributes": {"category": "language"}},
        {"local_id": "p", "kind": "project", "name": "Log parser"},
    ],
    "edges": [{"src": "s", "rel": "used_in", "dst": "p"}],
}


def main() -> int:
    """Send one message, show the proposal, review and commit it.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    app = create_app(engine=engine)
    app.state.model_factory = lambda _engine: TestModel(custom_output_args=SCRIPTED)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        body = client.post("/api/chat/messages", json={"text": STATEMENT}).json()
        proposal = body["proposal"]
        print(f"1. said      {STATEMENT!r} -> {body['reply']!r}")
        for op in proposal["operations"]:
            print(f"2. proposed  #{op['seq']} {op['op_type']} ({op['classification']})")
        with engine.connect() as conn:
            before = queries.table_counts(conn)
        if before["entity"] or before["edge"] or before["assertion"]:
            print("FAIL: knowledge written before review")
            return 1
        print("3. reviewed  nothing in the knowledge yet; accepting every operation")
        for op in proposal["operations"]:
            url = f"/api/proposals/{proposal['id']}/operations/{op['id']}/review"
            client.post(url, json={"decision": "accept"}).raise_for_status()
        client.post(f"/api/proposals/{proposal['id']}/commit").raise_for_status()
    with engine.connect() as conn:
        after = queries.table_counts(conn)
    print(f"4. committed entities={after['entity']} edges={after['edge']}")
    return 0 if (after["entity"], after["edge"]) == (2, 1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
