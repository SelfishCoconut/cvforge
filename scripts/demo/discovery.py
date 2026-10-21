"""Demo (FR-30, FR-32, M6): discovery questions and an interview feed the review pipeline, offline.

A synthetic profile records Python without any use; the posting asks for Rust (backed), Python
(undocumented) and Fortran (a gap). The model is a scripted stand-in. It exits non-zero if a gap
raises a discovery question, if an answer writes knowledge directly, or if declining writes.
"""

import tempfile
from pathlib import Path

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


def _seed(engine: sa.Engine) -> None:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    ev = apply.record_evidence(engine, source, "message:1", "I know Rust and Python.")
    ops = [
        {
            "seq": 0,
            "payload": {
                "evidence_id": ev,
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Rust",
            },
        },
        {
            "seq": 1,
            "payload": {
                "evidence_id": ev,
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Python",
            },
        },
        {
            "seq": 2,
            "payload": {
                "evidence_id": ev,
                "op_type": "create_entity",
                "kind": "project",
                "name": "Parser",
            },
        },
        {
            "seq": 3,
            "payload": {
                "evidence_id": ev,
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "used_in",
                "dst": {"op": 2},
            },
        },
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
    """Ask, answer, decline and interview; report what was written.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    _seed(engine)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(
        engine, page, JobAnalysis(required_skills=["Rust", "Python", "Fortran"])
    ).id
    replace_matches(engine, posting, match_posting(engine, posting) or [])
    scripted = {
        "reply": "Noted.",
        "facts": [{"local_id": "p", "kind": "skill", "name": "Go"}],
        "edges": [],
    }
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine)
        app.state.model_factory = lambda _e: TestModel(custom_output_args=scripted)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            asked = client.get(f"/api/jobs/{posting}/discovery").json()
            print(f"1. discovery  {[q['requirement_text'] for q in asked]} (the gap is not asked)")
            with engine.connect() as conn:
                before = queries.table_counts(conn)
            rid = asked[0]["requirement_id"]
            declined = client.post(f"/api/jobs/{posting}/discovery/{rid}/decline")
            print(f"2. decline    {declined.status_code}, nothing written")
            answered = client.post(
                f"/api/jobs/{posting}/discovery/{rid}/answer",
                json={"answer": "I used Python for ETL jobs at Acme."},
            ).json()
            print(f"3. answer     pending proposal #{answered['proposal']['id']}, not committed")
            interview = [
                q["requirement_text"] for q in client.get(f"/api/jobs/{posting}/interview").json()
            ]
            print(f"4. interview  asks about {interview}")
            with engine.connect() as conn:
                after = queries.table_counts(conn)
    wrote_knowledge = any(before[t] != after[t] for t in ("entity", "edge", "assertion"))
    print(f"5. knowledge  written without review: {wrote_knowledge}")
    ok = (
        [q["requirement_text"] for q in asked] == ["Python"]
        and declined.status_code == 204
        and answered["proposal"]["id"] is not None
        and interview == ["Python", "Fortran"]
        and not wrote_knowledge
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
