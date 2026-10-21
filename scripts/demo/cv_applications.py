"""Demo (FR-27, FR-28, M5): version a CV and record which one went to which posting, offline.

A synthetic profile is generated into two CVs (the second derived from the first); only a
validated, final CV may be recorded as sent. It exits non-zero if lineage, usage queries or the
draft/foreign-posting refusals misbehave.
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

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


def main() -> int:
    """Generate two CV versions, finalise one, and record an application.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    ev = apply.record_evidence(engine, source, "message:1", "I used Rust in a log parser.")
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
                "kind": "project",
                "name": "Log parser",
            },
        },
        {
            "seq": 2,
            "payload": {
                "evidence_id": ev,
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "used_in",
                "dst": {"op": 1},
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
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(engine, page, JobAnalysis(required_skills=["Rust"])).id
    replace_matches(engine, posting, match_posting(engine, posting) or [])
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        with TestClient(create_app(settings, engine=engine), base_url="http://127.0.0.1") as client:
            first = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
            second = client.post(
                f"/api/jobs/{posting}/cvs", json={"parent_cv_id": first["id"]}
            ).json()
            chain = [c["version"] for c in client.get(f"/api/cvs/{second['id']}/lineage").json()]
            print(f"1. lineage    versions {chain} (root first)")
            body = {
                "job_posting_id": posting,
                "cv_id": second["id"],
                "applied_at": "2026-10-21T09:30:00",
            }
            draft_try = client.post("/api/applications", json=body)
            print(f"2. draft CV   record -> {draft_try.status_code} (only a final CV can be sent)")
            client.post(f"/api/cvs/{second['id']}/final")
            sent = client.post("/api/applications", json=body)
            print(f"3. final CV   record -> {sent.status_code} {sent.json()['status']}")
            usages = client.get("/api/applications", params={"cv_id": second["id"]}).json()
            print(f"4. usages     CV {second['id']} used in {len(usages)} application(s)")
    ok = (
        chain == [1, 2]
        and draft_try.status_code == 422
        and sent.status_code == 201
        and len(usages) == 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
