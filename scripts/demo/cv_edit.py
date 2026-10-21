"""Demo (FR-31, M6): edit a CV in conversation without ever adding an unsupported fact, offline.

A scripted planner stands in for the model. A synthetic profile yields a CV; the demo rewords a
bullet (accepted), tries to reword one into a leadership claim (refused), asks to emphasise a
skill nothing stores (refused and redirected) and drops a required skill (new version fails
validation). It exits non-zero if any of that behaves differently.
"""

import tempfile
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, queries
from cvforge.kb.db import make_engine
from cvforge.kb.models import ProposalInput
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind
from cvforge.llm.schemas import JobAnalysis
from cvforge.match.store import replace_matches
from cvforge.match.verdicts import match_posting
from cvforge.web.fetch import FetchedPage


def _seed(engine: sa.Engine) -> None:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    ev = apply.record_evidence(engine, source, "message:1", "I built a Rust log parser.")

    def op(seq: int, **payload: object) -> dict[str, object]:
        return {"seq": seq, "payload": {"evidence_id": ev, **payload}}

    ops = [
        op(0, op_type="create_entity", kind="skill", name="Rust"),
        op(
            1,
            op_type="create_entity",
            kind="project",
            name="Log parser",
            summary="Parsed two gigabytes per second",
        ),
        op(2, op_type="add_edge", src={"op": 0}, rel="used_in", dst={"op": 1}),
    ]
    draft = ProposalInput.model_validate(
        {"origin": "chat", "source_id": source, "summary": "demo", "operations": ops}
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    for operation in record.operations if record else []:
        apply.review_operation(engine, operation.id, "accept")
    apply.commit_proposal(engine, proposal)


def main() -> int:
    """Run four edits against one CV and report each outcome.

    Returns:
        0 when every edit behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    _seed(engine)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(engine, page, JobAnalysis(required_skills=["Rust"])).id
    replace_matches(engine, posting, match_posting(engine, posting) or [])
    plan: dict[str, Any] = {"ops": [], "reply": "ok"}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(next(iter(info.output_tools)).name, plan)])

    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine)
        app.state.model_factory = lambda _e: FunctionModel(respond)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
            claims = {
                c["text"]: c["id"] for s in cv["sections"] for i in s["items"] for c in i["claims"]
            }
            bullet, skill = claims["Parsed two gigabytes per second"], claims["Rust"]

            def edit(*ops: dict[str, Any]) -> dict[str, Any]:
                plan["ops"] = list(ops)
                answer: dict[str, Any] = client.post(
                    f"/api/cvs/{cv['id']}/edit", json={"instruction": "x"}
                ).json()
                return answer

            good = edit(
                {"kind": "reword", "claim_id": bullet, "text": "Processed two gigabytes a second"}
            )
            version = good["cv"]["version"]
            print(f"1. reword     v{version}, issues {good['issues']}")
            lie = edit(
                {"kind": "reword", "claim_id": bullet, "text": "Led a team of 50 parsing logs"}
            )
            print(f"2. fabricate  new version {lie['cv']}, refused: {lie['refused'][0][:60]}...")
            ghost = edit({"kind": "emphasize", "name": "Kubernetes"})
            print(f"3. emphasise  Kubernetes -> {ghost['refused'][0][:60]}...")
            short = edit({"kind": "drop", "claim_id": skill})
            codes = [i["code"] for i in short["issues"]]
            final = client.post(f"/api/cvs/{short['cv']['id']}/final").status_code
            print(f"4. drop Rust  issues {codes}; finalise -> {final}")
    ok = (
        good["cv"]["version"] == 2
        and lie["cv"] is None
        and ghost["cv"] is None
        and codes == ["incomplete_coverage"]
        and final == 409
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
