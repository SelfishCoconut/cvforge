"""Demo (FR-20, M3): persist a posting, persist it again, and see one row and no knowledge.

Offline and in memory: the page and its analysis are synthetic, so no model and no network.
It exits non-zero if the second persist duplicated the posting, if the posting does not
point at a `web` source, or if anything reached the knowledge tables.
"""

import sqlalchemy as sa

from cvforge.jobs.store import persist_posting
from cvforge.kb import queries, schema
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import WorkModel
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

URL = "https://jobs.example.test/posting/42"


def main() -> int:
    """Persist a synthetic posting twice and report what the database holds.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    page = FetchedPage(URL, URL, "Backend Engineer", "Backend Engineer. Python, SQL.", "static")
    analysis = JobAnalysis(
        title="Backend Engineer",
        required_skills=["Python", "SQL"],
        preferred_skills=["Rust"],
        responsibilities=["Build data pipelines"],
        working_model=WorkModel.REMOTE,
    )
    first = persist_posting(engine, page, analysis)
    print(f"1. persisted  posting {first.id} (created={first.created})")
    print(f"              {first.requirement_count} requirements")
    second = persist_posting(engine, page, analysis)
    print(f"2. again      posting {second.id} (created={second.created}), same URL, no duplicate")
    with engine.connect() as conn:
        postings = conn.execute(sa.select(sa.func.count()).select_from(schema.job_posting)).scalar()
        kind = conn.execute(
            sa.select(schema.source.c.kind).where(schema.source.c.id == second.source_id)
        ).scalar()
        counts = queries.table_counts(conn)
    print(f"3. stored     {postings} posting, source kind {kind!r}")
    print(f"4. knowledge  entity={counts['entity']} edge={counts['edge']}")
    ok = postings == 1 and kind == "web" and counts["entity"] == counts["edge"] == 0
    return 0 if ok and not second.created else 1


if __name__ == "__main__":
    raise SystemExit(main())
