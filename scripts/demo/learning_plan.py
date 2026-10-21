"""Demo (FR-33, FR-34, M7): a learning plan for a gap, and completion that only proposes, offline.

A synthetic profile records Haskell as a gap. The model is a scripted stand-in. It exits non-zero
if a non-gap earns a plan, if tracking works before the skill is recorded as `learning`, if
finishing the plan changes the entity, or if no pending `set_state` proposal is raised.
"""

import tempfile
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

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

PLAN = {
    "summary": "Learn the basics, then build something small.",
    "steps": [
        {"title": "Read a tutorial", "kind": "reading", "done_when": "You can explain monads"},
        {"title": "Build a parser", "kind": "project", "done_when": "It parses a sample file"},
    ],
}


def _commit(engine: sa.Engine, source: int, evidence: int, *payloads: dict[str, Any]) -> list[int]:
    ops = [{"seq": i, "payload": {"evidence_id": evidence, **p}} for i, p in enumerate(payloads)]
    draft = ProposalInput.model_validate(
        {"origin": "chat", "source_id": source, "summary": "demo", "operations": ops}
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    for operation in record.operations if record else []:
        apply.review_operation(engine, operation.id, "accept")
    ids = apply.commit_proposal(engine, proposal).entity_ids
    return [ids[i] for i in sorted(ids)]


def main() -> int:
    """Plan a gap, try to track it too early, then record it as learning and finish the plan.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    ev = apply.record_evidence(engine, source, "message:1", "Haskell is not something I know yet.")
    (haskell,) = _commit(
        engine, source, ev,
        {"op_type": "create_entity", "kind": "skill", "name": "Haskell", "state": "gap"},
    )  # fmt: skip
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(engine, page, JobAnalysis(required_skills=["Haskell"])).id
    replace_matches(engine, posting, match_posting(engine, posting) or [])
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine)
        app.state.model_factory = lambda _e: TestModel(custom_output_args=PLAN)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            rid = client.get(f"/api/jobs/{posting}/gaps").json()[0]["requirement_id"]
            plan = client.post(f"/api/jobs/{posting}/gaps/{rid}/plan").json()
            print(
                f"1. plan       {len(plan['steps'])} steps for requirement {rid}: {plan['summary']}"
            )
            first, second = (s["id"] for s in plan["steps"])
            early = client.post(f"/api/plans/{plan['id']}/steps/{first}/complete")
            print(f"2. too early  {early.status_code} (the skill is a gap, not 'learning')")
            _commit(
                engine, source, ev, {"op_type": "set_state", "entity": haskell, "state": "learning"}
            )
            client.post(f"/api/plans/{plan['id']}/steps/{first}/complete")
            done = client.post(f"/api/plans/{plan['id']}/steps/{second}/complete").json()
            print(
                f"3. finished   pending proposal #{done['proposal']['id']}: "
                f"{[o['op_type'] for o in done['proposal']['operations']]}"
            )
            with engine.connect() as conn:
                entity = queries.get_entity(conn, haskell)
            state = entity.state.value if entity else "?"
            print(f"4. entity     still {state!r} until the proposal is accepted")
    ok = early.status_code == 409 and done["proposal"]["id"] is not None and state == "learning"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
