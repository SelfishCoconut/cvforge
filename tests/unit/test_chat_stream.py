"""`POST /api/chat/messages/stream` streams the reply as NDJSON (FR-13)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

from cvforge.api.chat import stream_events
from cvforge.kb import queries

REPLY = "Noted: you know Rust."
OUTPUT = {"reply": REPLY, "facts": [{"local_id": "s", "kind": "skill", "name": "Rust"}]}


def _model(output: dict[str, Any], *, fail_after: int | None = None) -> Model:
    raw = json.dumps(output)
    chunks = [raw[i : i + 7] for i in range(0, len(raw), 7)]

    async def stream(_m: list[ModelMessage], info: AgentInfo) -> AsyncIterator[DeltaToolCalls]:
        name = info.output_tools[0].name
        for index, chunk in enumerate(chunks):
            if fail_after is not None and index == fail_after:
                raise RuntimeError("connection reset")
            yield {0: DeltaToolCall(name=name if index == 0 else None, json_args=chunk)}

    return FunctionModel(stream_function=stream)


def _events(client: TestClient, model: Model, text: str = "I know Rust") -> list[dict[str, Any]]:
    client.app.state.model_factory = lambda _e: model  # type: ignore[attr-defined]
    response = client.post("/api/chat/messages/stream", json={"text": text})
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def _counts(kb: sa.Engine) -> dict[str, int]:
    with kb.connect() as conn:
        return queries.table_counts(conn)


def test_deltas_concatenate_to_the_reply_then_proposal_then_done(client: TestClient) -> None:
    events = _events(client, _model(OUTPUT))

    assert [e["type"] for e in events][-2:] == ["proposal", "done"]
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == REPLY
    proposal = next(e for e in events if e["type"] == "proposal")
    assert len(proposal["proposal"]["operations"]) == 1


def test_an_invalid_final_output_is_an_error_and_no_proposal(
    client: TestClient, kb: sa.Engine
) -> None:
    bad = {"reply": "hi", "facts": [{"local_id": "x", "kind": "hobby", "name": "Chess"}]}

    events = _events(client, _model(bad))

    assert events[-1]["type"] == "error"
    assert "proposal" not in {e["type"] for e in events}
    assert _counts(kb)["proposal"] == 0


def test_a_mid_stream_failure_is_an_error_and_no_proposal(
    client: TestClient, kb: sa.Engine
) -> None:
    events = _events(client, _model(OUTPUT, fail_after=4))

    assert events[-1]["type"] == "error" and "connection reset" in events[-1]["message"]
    assert {"proposal", "done"}.isdisjoint(e["type"] for e in events)
    assert _counts(kb)["proposal"] == 0


@pytest.mark.parametrize("text", ["   ", "x" * 200_000])
def test_the_same_validation_applies(client: TestClient, kb: sa.Engine, text: str) -> None:
    response = client.post("/api/chat/messages/stream", json={"text": text})

    assert response.status_code == 422 and _counts(kb)["source"] == 0


def test_an_unknown_conversation_is_a_404_not_a_stream(client: TestClient) -> None:
    response = client.post("/api/chat/messages/stream", json={"text": "x", "conversation_id": 99})

    assert response.status_code == 404


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_a_disconnect_leaves_no_half_written_proposal(kb: sa.Engine) -> None:
    from cvforge.kb import apply
    from cvforge.kb.vocab import SourceKind

    source = apply.record_source(kb, SourceKind.CONVERSATION, "c")
    evidence = apply.record_evidence(kb, source, "message:1", "I know Rust")
    stream = stream_events(kb, None, lambda _e: _model(OUTPUT), "I know Rust", source, evidence)

    first = json.loads(await anext(stream))
    await stream.aclose()  # the client went away

    assert first["type"] == "delta"
    assert _counts(kb)["proposal"] == 0
