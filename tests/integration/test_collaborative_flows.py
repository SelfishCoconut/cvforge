"""Discovery, interview and CV editing through the real app over a migrated database (M6)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from tests.support.profile import build_profile_with, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import queries

pytestmark = pytest.mark.integration


def test_discovery_interview_and_edit_over_a_migrated_file(tmp_path: Path, open_db: Any) -> None:
    engine = open_db(tmp_path / "cvforge.db")
    build_profile_with(engine)
    posting = matched_posting(engine, "Rust", "Python", "Fortran")
    plan: dict[str, Any] = {"reply": "ok", "facts": [], "edges": []}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(next(iter(info.output_tools)).name, plan)])

    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=engine)
    app.state.model_factory = lambda _e: FunctionModel(respond)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        asked = client.get(f"/api/jobs/{posting}/discovery").json()
        assert [q["requirement_text"] for q in asked] == ["Python"]
        plan["facts"] = [{"local_id": "p", "kind": "skill", "name": "Go"}]
        answer = client.post(
            f"/api/jobs/{posting}/discovery/{asked[0]['requirement_id']}/answer",
            json={"answer": "I used Python at Acme."},
        )
        assert answer.status_code == 200 and answer.json()["proposal"]["id"] is not None
        interview = client.get(f"/api/jobs/{posting}/interview").json()
        assert {q["verdict"] for q in interview} == {"undocumented", "gap"}

        cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
        bullet = next(
            c
            for s in cv["sections"]
            for i in s["items"]
            for c in i["claims"]
            if c["text"] == "Parsed two gigabytes per second"
        )
        plan.clear()
        plan.update(
            {
                "reply": "ok",
                "ops": [
                    {
                        "kind": "reword",
                        "claim_id": bullet["id"],
                        "text": "Parsed two gigabytes a second",
                    }
                ],
            }
        )
        edited = client.post(f"/api/cvs/{cv['id']}/edit", json={"instruction": "tweak"}).json()
        assert edited["cv"]["version"] == 2 and edited["issues"] == []

    with engine.connect() as conn:
        counts = queries.table_counts(conn)
    assert counts["proposal"] >= 1
