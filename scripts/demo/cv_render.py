"""Demo (FR-26, M5): render a CV as LaTeX, PDF and plain text, with special characters escaped.

Offline. Needs `latexmk` (a TeX distribution). A synthetic profile whose names contain `&`,
`%` and `_` is generated into a CV and rendered into a temporary `cv_out/`. It exits non-zero
if the PDF is not a PDF, if the text rendering lacks a claim the LaTeX has, or if LaTeX markup
leaks into the plain text.
"""

import tempfile
from pathlib import Path

import sqlalchemy as sa
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


def _seed(engine: sa.Engine) -> None:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    ev = apply.record_evidence(engine, source, "message:1", "I use C&C++ at R&D_Lab for 100%.")

    def op(seq: int, **payload: object) -> dict[str, object]:
        return {"seq": seq, "payload": {"evidence_id": ev, **payload}}

    ops = [
        op(0, op_type="create_entity", kind="skill", name="C&C++"),
        op(
            1,
            op_type="create_entity",
            kind="project",
            name="R&D_Lab tooling",
            summary="Reached 100% coverage",
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
    """Generate and render a CV, then check the three files agree.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    _seed(engine)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(engine, page, JobAnalysis(required_skills=["C&C++"])).id
    replace_matches(engine, posting, match_posting(engine, posting) or [])
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(
            data_dir=Path(scratch) / "data",
            frontend_dist=Path(scratch) / "none",
            cv_out_dir=Path(scratch) / "cv_out",
        )
        with TestClient(create_app(settings, engine=engine), base_url="http://127.0.0.1") as client:
            cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
            files = client.post(f"/api/cvs/{cv['id']}/render").json()
        tex = Path(files["tex"]).read_text()
        txt = Path(files["txt"]).read_text()
        pdf = Path(files["pdf"]).read_bytes()
        print(f"1. wrote      {sorted(Path(p).name for p in files.values())} under cv_out/")
        print(f"2. pdf        {len(pdf)} bytes, starts {pdf[:5]!r}")
        print(f"3. escaped    {r'C\&C++' in tex}  plain text: {txt.splitlines()[0]!r}")
    ok = pdf.startswith(b"%PDF") and r"C\&C++" in tex and "C&C++" in txt and "\\" not in txt
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
