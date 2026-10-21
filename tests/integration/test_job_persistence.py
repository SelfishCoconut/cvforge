"""FR-20: persistence against a real, migrated database file (migration 0003 matches the code)."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa

from cvforge.jobs.store import persist_posting
from cvforge.kb import schema
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

pytestmark = pytest.mark.integration

OpenDb = Callable[..., sa.Engine]


def _count(engine: sa.Engine, table: sa.Table) -> int | None:
    with engine.connect() as conn:
        return conn.execute(sa.select(sa.func.count()).select_from(table)).scalar()


def test_a_posting_persists_and_dedupes_in_a_migrated_database(
    tmp_path: Path, open_db: OpenDb
) -> None:
    engine = open_db(tmp_path / "cvforge.db")
    url = "https://jobs.example.test/1"
    page = FetchedPage(url, url, "J", "t", "static")
    analysis = JobAnalysis(title="Engineer", required_skills=["Python"])

    first = persist_posting(engine, page, analysis)
    second = persist_posting(engine, page, analysis)

    assert (first.created, second.created, second.id) == (True, False, first.id)
    assert _count(engine, schema.job_posting) == 1
    assert _count(engine, schema.requirement) == 1
