"""FR-20: a fetched, analysed posting is persisted with its requirements, deduplicated by URL."""

import pytest
import sqlalchemy as sa

from cvforge.jobs.store import decompose, normalize_url, persist_posting
from cvforge.kb import queries, schema
from cvforge.kb.vocab import RequirementKind, SourceKind, WorkModel
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

URL = "https://Jobs.Example.test/posting/42#apply"
ANALYSIS = JobAnalysis(
    title="Senior Backend Engineer",
    required_skills=["Python", "SQL"],
    preferred_skills=["Rust"],
    responsibilities=["Build data pipelines"],
    experience_requirements=["5+ years"],
    working_model=WorkModel.REMOTE,
)


def _page(text: str = "Senior Backend Engineer. Python, SQL.") -> FetchedPage:
    return FetchedPage(URL, "https://jobs.example.test/posting/42", "Job", text, "static")


def _rows(engine: sa.Engine, table: sa.Table) -> list[sa.Row[tuple[object, ...]]]:
    with engine.connect() as conn:
        return list(conn.execute(sa.select(table)))


def test_persisting_creates_one_posting_and_a_requirement_per_kind_present(kb: sa.Engine) -> None:
    stored = persist_posting(kb, _page(), ANALYSIS)

    assert stored.created and stored.requirement_count == 5
    (posting,) = _rows(kb, schema.job_posting)
    assert posting.title == "Senior Backend Engineer" and posting.work_model == "remote"
    assert posting.url == "https://jobs.example.test/posting/42"
    kinds = {row.kind for row in _rows(kb, schema.requirement)}
    assert kinds == {"required", "preferred", "responsibility"}


def test_the_posting_points_at_a_web_source_for_the_raw_page(kb: sa.Engine) -> None:
    stored = persist_posting(kb, _page(), ANALYSIS)

    (posting,) = _rows(kb, schema.job_posting)
    assert posting.source_id == stored.source_id
    with kb.connect() as conn:
        source = conn.execute(
            sa.select(schema.source).where(schema.source.c.id == stored.source_id)
        ).one()
    assert source.kind == SourceKind.WEB.value
    assert source.uri == "https://jobs.example.test/posting/42"
    assert posting.raw_text == "Senior Backend Engineer. Python, SQL."


def test_persisting_the_same_url_again_updates_the_posting_instead_of_duplicating(
    kb: sa.Engine,
) -> None:
    first = persist_posting(kb, _page(), ANALYSIS)
    changed = JobAnalysis(title="Staff Backend Engineer", required_skills=["Go"])

    second = persist_posting(
        kb, _page("Staff role. Go."), changed, url="https://jobs.example.test/posting/42"
    )

    assert (second.id, second.created) == (first.id, False)
    assert second.source_id != first.source_id
    (posting,) = _rows(kb, schema.job_posting)
    assert posting.title == "Staff Backend Engineer" and posting.raw_text == "Staff role. Go."
    assert [(r.kind, r.text) for r in _rows(kb, schema.requirement)] == [("required", "Go")]


def test_persisting_writes_no_knowledge(kb: sa.Engine) -> None:
    persist_posting(kb, _page(), ANALYSIS)
    with kb.connect() as conn:
        counts = queries.table_counts(conn)
    assert (counts["entity"], counts["edge"], counts["assertion"]) == (0, 0, 0)


def test_a_requirement_kind_outside_the_closed_set_is_rejected(kb: sa.Engine) -> None:
    stored = persist_posting(kb, _page(), ANALYSIS)
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.requirement).values(
                job_posting_id=stored.id, kind="nice_to_have", text="Haskell"
            )
        )


def test_a_posting_must_reference_an_existing_source(kb: sa.Engine) -> None:
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.job_posting).values(
                url="https://x.test/1",
                source_id=999,
                raw_text="t",
                analysis_json="{}",
                fetched_at=sa.func.now(),
            )
        )


def test_a_posting_with_no_requirements_is_still_stored(kb: sa.Engine) -> None:
    stored = persist_posting(kb, _page(), JobAnalysis())
    assert stored.requirement_count == 0
    assert _rows(kb, schema.requirement) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Jobs.Example.test/a?id=7#frag", "https://jobs.example.test/a?id=7"),
        ("https://jobs.example.test:443/a", "https://jobs.example.test/a"),
        ("http://jobs.example.test:8080", "http://jobs.example.test:8080/"),
        ("https://[::1]/a", "https://[::1]/a"),
    ],
)
def test_url_normalisation(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_decomposition_is_ordered_and_deduplicated_within_a_kind() -> None:
    analysis = JobAnalysis(
        required_skills=["Python", "Python"], preferred_skills=["Python"], responsibilities=["Ship"]
    )
    assert decompose(analysis) == [
        (RequirementKind.REQUIRED, "Python"),
        (RequirementKind.PREFERRED, "Python"),
        (RequirementKind.RESPONSIBILITY, "Ship"),
    ]
