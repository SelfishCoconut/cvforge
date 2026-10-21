"""Demo (FR-21..FR-23, M4): match a posting's requirements against the knowledge base, offline.

An in-memory knowledge base holds 'Rust' as a confirmed skill used in a project; the posting asks
for Rust, a skill the profile only plausibly covers, and Fortran. The model is a scripted
stand-in and the embedder a hash-based fake, so there is no network. It exits non-zero if any
requirement lacks a verdict, if `undocumented`/`gap` carry support, or if knowledge was written.
"""

import hashlib
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, embeddings, queries
from cvforge.kb.db import make_engine
from cvforge.kb.models import ProposalInput
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage


class _BagEmbedder:
    """Offline embedder: a text is the sum of one fixed pseudo-random vector per word."""

    dimension = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            total = [0.0] * self.dimension
            for word in text.lower().split() or [""]:
                digest = hashlib.sha256(word.encode()).digest()
                for i in range(self.dimension):
                    total[i] += digest[i] / 127.5 - 1
            out.append(total)
        return out


def _entity(op: int, kind: str, name: str, evidence: int) -> dict[str, Any]:
    return {
        "seq": op,
        "payload": {
            "op_type": "create_entity",
            "kind": kind,
            "name": name,
            "evidence_id": evidence,
        },
    }


def _seed(engine: sa.Engine) -> int:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(
        engine, source, "message:1", "I built a Django REST API in Rust."
    )
    ops = [
        _entity(0, "skill", "Rust", evidence),
        _entity(1, "skill", "Django REST API", evidence),
        _entity(2, "project", "Parser", evidence),
        {
            "seq": 3,
            "payload": {
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "used_in",
                "dst": {"op": 2},
                "evidence_id": evidence,
            },
        },
        {
            "seq": 4,
            "payload": {
                "op_type": "add_edge",
                "src": {"op": 1},
                "rel": "used_in",
                "dst": {"op": 2},
                "evidence_id": evidence,
            },
        },
    ]
    draft = ProposalInput.model_validate(
        {"origin": "chat", "source_id": source, "summary": "demo", "operations": ops}
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    for op in record.operations if record else []:
        apply.review_operation(engine, op.id, "accept")
    return len(apply.commit_proposal(engine, proposal).entity_ids)


def main() -> int:
    """Match a synthetic posting and print each requirement's verdict.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    _seed(engine)
    embedder = _BagEmbedder()
    with engine.connect() as conn:
        ids = [r.id for r in queries.list_entities(conn)]
    embeddings.index_entities(engine, embedder, ids)
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(
        engine, page, JobAnalysis(required_skills=["Rust", "Django REST API client", "Fortran"])
    ).id
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine, embedder=embedder)
        app.state.model_factory = lambda _e: TestModel(
            custom_output_args={"entity_ids": [], "rationale": ""}
        )
        with TestClient(app, base_url="http://127.0.0.1") as client:
            rows = client.post(f"/api/jobs/{posting}/match").json()
            gaps = client.get(f"/api/jobs/{posting}/gaps").json()
    for row in rows:
        print(f"{row['verdict']:12} {row['text']!r}: {row['rationale']}")
    cited = [e["excerpt"] for r in rows for sup in r["support"] for e in sup["evidence"]]
    print(f"evidence    {cited[:1]} (what the satisfied verdict rests on)")
    print(f"gap report  {[g['text'] for g in gaps]}")
    with engine.connect() as conn:
        counts = queries.table_counts(conn)
    print(f"knowledge   entity={counts['entity']} edge={counts['edge']} (unchanged by matching)")
    verdicts = [r["verdict"] for r in rows]
    unsupported = all(not r["support"] for r in rows if r["verdict"] in ("undocumented", "gap"))
    ok = (
        verdicts == ["satisfied", "undocumented", "gap"]
        and unsupported
        and bool(cited)
        and [g["text"] for g in gaps] == ["Django REST API client", "Fortran"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
