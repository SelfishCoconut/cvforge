"""Demo (FR-01..FR-12, M1a): one statement goes intake -> proposal -> review -> commit.

Fully offline and in memory: no model, no network, and it never touches
`data/cvforge.db`. It prints each stage so the review flow can be seen, and
exits non-zero if any stage behaves differently than the design says it must.
"""

import json

from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.kb import apply
from cvforge.kb.db import make_engine
from cvforge.kb.models import ProposalDraft
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind

STATEMENT = "I built a log parser in Rust while working at Acme Logistics."


def main() -> int:
    """Run the pipeline end to end through the HTTP API.

    Returns:
        0 when every stage behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)

    source = apply.record_source(engine, SourceKind.CONVERSATION, "demo chat")
    evidence = apply.record_evidence(engine, source, "message:1", STATEMENT)
    print(f"1. intake    source={source} evidence={evidence}: {STATEMENT!r}")

    # In M1b an agent produces this draft; here it is written out by hand.
    ops: list[dict[str, object]] = [
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
        {"op_type": "create_entity", "kind": "project", "name": "Log parser"},
        {"op_type": "create_entity", "kind": "organization", "name": "Acme Logistics"},
        {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
        {"op_type": "add_edge", "src": {"op": 1}, "rel": "at_organization", "dst": {"op": 2}},
    ]
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "Rust, a log parser, and Acme Logistics",
            "operations": [
                {"seq": i, "payload": {**op, "evidence_id": evidence}, "classification": "new"}
                for i, op in enumerate(ops)
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    print(f"2. proposal  #{proposal} with {len(ops)} pending operations; nothing stored yet")

    with TestClient(create_app(engine=engine)) as client:
        empty = client.get("/api/entities").json()
        operations = client.get(f"/api/proposals/{proposal}").json()["operations"]
        for op in operations:
            # The reviewer drops the employer, and the edge that needed it.
            decision = "reject" if op["seq"] in (2, 4) else "accept"
            client.post(
                f"/api/proposals/{proposal}/operations/{op['id']}/review",
                json={"decision": decision},
            )
        print("3. review    accepted seq 0, 1, 3; rejected seq 2, 4")
        committed = client.post(f"/api/proposals/{proposal}/commit").json()
        print(f"4. commit    {json.dumps(committed)}")
        entities = client.get("/api/entities").json()
        rust = committed["entity_ids"]["0"]
        origin = client.get(f"/api/provenance/entity/{rust}").json()[0]
    print(f"5. stored    {[e['name'] for e in entities]}")
    print(
        f"6. why?      Rust <- {origin['source_kind']} {origin['locator']}: {origin['excerpt']!r}"
    )

    ok = (
        empty == []
        and [e["name"] for e in entities] == ["Rust", "Log parser"]
        and origin["excerpt"] == STATEMENT
    )
    print("OK" if ok else "UNEXPECTED RESULT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
