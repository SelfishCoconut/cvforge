"""A chat message, reviewed and committed, resolves back to the message text (FR-03, FR-11)."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

pytestmark = pytest.mark.integration


def test_a_committed_assertion_resolves_back_to_the_message(client: TestClient) -> None:
    output = {
        "reply": "Noted.",
        "facts": [{"local_id": "s", "kind": "skill", "name": "Rust"}],
        "edges": [],
    }
    client.app.state.model_factory = lambda _e: TestModel(custom_output_args=output)  # type: ignore[attr-defined]
    text = "I wrote a parser in Rust"
    body = client.post("/api/chat/messages", json={"text": text}).json()
    proposal_id = body["proposal"]["id"]
    (op,) = body["proposal"]["operations"]

    review = client.post(
        f"/api/proposals/{proposal_id}/operations/{op['id']}/review", json={"decision": "accept"}
    )
    commit = client.post(f"/api/proposals/{proposal_id}/commit")

    assert review.status_code == 200 and commit.status_code == 200, (review.text, commit.text)
    entity_id = commit.json()["entity_ids"][str(op["seq"])]
    provenance = client.get(f"/api/provenance/entity/{entity_id}").json()
    assert text in str(provenance)
