"""Demo (FR-10, FR-13, C1): the whole UI loop against a scripted model on a temp database.

Serves the built SPA and the API on 127.0.0.1 until interrupted, with a scripted
stand-in for the model (no Ollama, no network). Nothing here is a switch in
production code: the app comes from the normal `create_app` factory and the fake
model is injected through `app.state.model_factory`, as in `chat_ingest.py`.

`--check` boots the same app in process, drives chat -> review -> commit ->
knowledge -> provenance over HTTP and prints `ok`. It needs no built frontend.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata

STATEMENT = "I worked at Acme as a backend engineer using Python"
# `excerpt` is read by the document agent and ignored by the chat agent, so one script
# serves both: each quote below is a passage of STATEMENT, which is also the upload text.
SCRIPTED = {
    "reply": "Noted: backend engineer at Acme, using Python.",
    "facts": [
        {"local_id": "o", "kind": "organization", "name": "Acme", "excerpt": "Acme"},
        {
            "local_id": "r",
            "kind": "role",
            "name": "Backend engineer",
            "excerpt": "backend engineer",
        },
        {
            "local_id": "s",
            "kind": "skill",
            "name": "Python",
            "attributes": {"category": "language"},
            "excerpt": "Python",
        },
    ],
    "edges": [
        {
            "src": "r",
            "rel": "at_organization",
            "dst": "o",
            "excerpt": "worked at Acme as a backend engineer",
        },
        {"src": "s", "rel": "used_in", "dst": "r", "excerpt": "backend engineer using Python"},
    ],
}


def build_app(data_dir: Path, frontend_dist: Path | None = None) -> FastAPI:
    """Build the real app on a fresh database in `data_dir`, with the scripted model.

    Args:
        data_dir: Directory for the throwaway database.
        frontend_dist: Built SPA to serve; the app default when omitted.

    Returns:
        The application, its model factory replaced by the scripted one.
    """
    engine = make_engine(data_dir / "demo.db")
    metadata.create_all(engine)
    settings = Settings(data_dir=data_dir)
    if frontend_dist is not None:
        settings = Settings(data_dir=data_dir, frontend_dist=frontend_dist)
    app = create_app(settings, engine=engine)
    app.state.model_factory = lambda _engine: TestModel(custom_output_args=SCRIPTED)
    return app


def _require(condition: bool, detail: object) -> None:
    """Fail the demo loudly when a step did not behave as the design says.

    Args:
        condition: What must hold.
        detail: Shown when it does not.

    Raises:
        AssertionError: `condition` is false.
    """
    if not condition:
        raise AssertionError(detail)


def _events(client: TestClient, text: str) -> list[dict[str, Any]]:
    """POST one chat message to the streaming endpoint and parse the NDJSON."""
    with client.stream("POST", "/api/chat/messages/stream", json={"text": text}) as response:
        response.raise_for_status()
        return [json.loads(line) for line in response.iter_lines() if line]


def run_loop(client: TestClient) -> int:
    """Drive chat -> review -> commit -> knowledge -> provenance and assert each step.

    Args:
        client: A client of an app whose model is the scripted one.

    Returns:
        The id of the committed `Python` entity.

    Raises:
        AssertionError: A step behaved differently than the design says it must.
    """
    events = _events(client, STATEMENT)
    kinds = [e["type"] for e in events]
    _require(kinds[-2:] == ["proposal", "done"], kinds)
    _require("delta" in kinds, kinds)
    proposal = events[-2]
    pid = proposal["proposal"]["id"]

    open_ids = [p["id"] for p in client.get("/api/proposals", params={"status": "open"}).json()]
    _require(pid in open_ids, open_ids)
    _require(client.get("/api/entities").json() == [], "knowledge written before review")

    detail = client.get(f"/api/proposals/{pid}").json()
    for op in detail["operations"]:
        reviewed = client.post(
            f"/api/proposals/{pid}/operations/{op['id']}/review", json={"decision": "accept"}
        )
        _require(reviewed.status_code == 200, reviewed.text)
    committed = client.post(f"/api/proposals/{pid}/commit")
    _require(committed.status_code == 200, committed.text)

    entities = {e["name"]: e["id"] for e in client.get("/api/entities").json()}
    _require(set(entities) == {"Acme", "Backend engineer", "Python"}, entities)
    origin = client.get(f"/api/provenance/entity/{entities['Python']}").json()
    _require(bool(origin) and {o["excerpt"] for o in origin} == {STATEMENT}, origin)

    again = client.post(f"/api/proposals/{pid}/commit")
    _require(again.status_code == 409, again.status_code)
    return int(entities["Python"])


def run_document_loop(client: TestClient) -> None:
    """Upload a document that restates what chat already committed, and re-ingest it cleanly.

    Run after `run_loop`. Acme and Python are identified by name, so they classify `known`;
    a role is not (two roles with one title are usually different jobs), so the role and the
    edges that touch it classify `new`. Committing must add exactly that one entity, and each
    fact must cite the exact passage it was read from (FR-14, FR-15, FR-16).

    Args:
        client: A client of an app whose model is the scripted one.

    Raises:
        AssertionError: A step behaved differently than the design says it must.
    """
    before = len(client.get("/api/entities").json())
    uploaded = client.post("/api/documents", files={"file": ("cv.md", STATEMENT.encode())})
    _require(uploaded.status_code == 201, uploaded.text)
    extracted = client.post(f"/api/documents/{uploaded.json()['source_id']}/extract")
    _require(extracted.status_code == 200, extracted.text)
    body = extracted.json()
    proposal = body["proposal"]
    classes = [op["classification"] for op in proposal["operations"]]
    expected = ["known", "new", "known", "new", "new"]
    _require(classes == expected and body["rejected"] == [], (classes, body["rejected"]))
    for op in proposal["operations"]:
        url = f"/api/proposals/{proposal['id']}/operations/{op['id']}/review"
        _require(client.post(url, json={"decision": "accept"}).status_code == 200, op)
    committed = client.post(f"/api/proposals/{proposal['id']}/commit")
    _require(committed.status_code == 200, committed.text)
    entities = client.get("/api/entities").json()
    _require(len(entities) == before + 1, "only the role should have been created")
    python = next(e["id"] for e in entities if e["name"] == "Python")
    cited = {o["excerpt"] for o in client.get(f"/api/provenance/entity/{python}").json()}
    _require({STATEMENT, "Python"} <= cited, cited)


def check() -> int:
    """Boot the app in process on a temp database and run the loop.

    Returns:
        0 on success; an assertion failure propagates.
    """
    with tempfile.TemporaryDirectory() as tmp:
        app = build_app(Path(tmp))
        with TestClient(app, base_url="http://127.0.0.1") as client:
            run_loop(client)
            run_document_loop(client)
    print("ok")
    return 0


def serve(port: int) -> int:
    """Serve the SPA and API on 127.0.0.1 until interrupted.

    Args:
        port: TCP port to bind.

    Returns:
        0 after a clean shutdown.
    """
    with tempfile.TemporaryDirectory() as tmp:
        app = build_app(Path(tmp), Settings().frontend_dist)
        print(f"CVForge demo (scripted model, throwaway database): http://127.0.0.1:{port}/")
        print(f"try: send '{STATEMENT}'")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Arguments; `sys.argv[1:]` when omitted.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="drive the loop in process, then exit")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return check() if args.check else serve(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
