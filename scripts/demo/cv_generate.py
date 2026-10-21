"""Demo (FR-24, FR-25, FR-29, M5): generate a CV from stored facts only, offline.

A synthetic profile is committed through the real pipeline (Rust used in a log parser at Acme;
Haskell recorded as a gap). The posting asks for Rust, Haskell and Fortran. The demo exits
non-zero if Haskell or Fortran appear in the CV, if any claim lacks an assertion about its
entity, if a tampered CV validates, or if generating wrote any knowledge.
"""

import tempfile
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, queries, schema
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
    ev = apply.record_evidence(engine, source, "message:1", "At Acme I built a Rust log parser.")

    def op(seq: int, **payload: object) -> dict[str, object]:
        return {"seq": seq, "payload": {"evidence_id": ev, **payload}}

    ops = [
        op(0, op_type="create_entity", kind="skill", name="Rust"),
        op(1, op_type="create_entity", kind="skill", name="Haskell", state="gap"),
        op(
            2,
            op_type="create_entity",
            kind="role",
            name="Backend Engineer",
            attributes={"started_at": "2019-01-01", "ended_at": "2022-06-30"},
        ),
        op(3, op_type="create_entity", kind="organization", name="Acme Logistics"),
        op(
            4,
            op_type="create_entity",
            kind="project",
            name="Log parser",
            summary="Parsed two gigabytes per second",
        ),
        op(5, op_type="add_edge", src={"op": 0}, rel="used_in", dst={"op": 4}),
        op(6, op_type="add_edge", src={"op": 4}, rel="part_of", dst={"op": 2}),
        op(7, op_type="add_edge", src={"op": 2}, rel="at_organization", dst={"op": 3}),
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
    """Generate, validate, tamper with and re-validate a CV.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    _seed(engine)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(
        engine, page, JobAnalysis(required_skills=["Rust", "Haskell", "Fortran"])
    ).id
    results = match_posting(engine, posting)
    replace_matches(engine, posting, results or [])
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        with TestClient(create_app(settings, engine=engine), base_url="http://127.0.0.1") as client:
            with engine.connect() as conn:
                before = queries.table_counts(conn)
            cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
            lines = [c["text"] for s in cv["sections"] for i in s["items"] for c in i["claims"]]
            print(f"1. generated  CV v{cv['version']}: {lines}")
            first = cv["sections"][0]["items"][0]["claims"][0]
            detail = client.get(f"/api/cvs/{cv['id']}/claims/{first['id']}").json()
            print(f"2. traced     {first['text']!r} <- {detail['evidence']['excerpt']!r}")
            valid = client.post(f"/api/cvs/{cv['id']}/validate").json()["valid"]
            print(f"3. validates  {valid}")
            with engine.begin() as conn:
                conn.execute(
                    sa.update(schema.cv_claim)
                    .where(schema.cv_claim.c.text == "Rust")
                    .values(text="Rust expert")
                )
            refused = client.post(f"/api/cvs/{cv['id']}/final")
            print(f"4. tampered   final -> {refused.status_code}")
            with engine.connect() as conn:
                after = queries.table_counts(conn)
    unchanged = all(before[t] == after[t] for t in ("entity", "edge", "assertion", "proposal"))
    print(f"5. knowledge  unchanged by generation: {unchanged}")
    ok = (
        "Haskell" not in str(lines)
        and "Fortran" not in str(lines)
        and "Rust" in lines
        and valid
        and refused.status_code == 409
        and unchanged
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
