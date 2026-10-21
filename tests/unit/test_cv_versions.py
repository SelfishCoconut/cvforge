"""FR-27: CVs are versioned per posting, with parent links that always terminate at a root."""

from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.cv.store import WrongPostingError, get_cv, list_cvs, save_cv
from cvforge.cv.versions import LineageError, lineage
from cvforge.jobs.store import persist_posting
from cvforge.kb import schema
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage


def _setup(kb: sa.Engine, propose: Any) -> int:
    build_profile(kb, propose)
    return matched_posting(kb, "Rust")


def _save(kb: sa.Engine, posting: int, parent: int | None = None) -> int:
    return save_cv(kb, posting, generate_cv(kb, posting), parent_cv_id=parent)


def test_a_postings_first_cv_is_version_one_with_no_parent(kb: sa.Engine, propose: Any) -> None:
    posting = _setup(kb, propose)
    cv = get_cv(kb, _save(kb, posting))
    assert cv is not None and (cv.version, cv.parent_cv_id) == (1, None)


def test_a_cv_from_a_prior_one_records_the_parent_and_increments_the_version(
    kb: sa.Engine, propose: Any
) -> None:
    posting = _setup(kb, propose)
    first = _save(kb, posting)
    second = get_cv(kb, _save(kb, posting, first))
    assert second is not None and (second.version, second.parent_cv_id) == (2, first)


def test_walking_parents_ends_at_a_root_in_order(kb: sa.Engine, propose: Any) -> None:
    posting = _setup(kb, propose)
    a = _save(kb, posting)
    b = _save(kb, posting, a)
    c = _save(kb, posting, b)
    assert [cv.id for cv in lineage(kb, c)] == [a, b, c]
    assert [cv.id for cv in lineage(kb, a)] == [a]


def test_listing_orders_by_version_with_lineage_intact(kb: sa.Engine, propose: Any) -> None:
    posting = _setup(kb, propose)
    a = _save(kb, posting)
    b = _save(kb, posting, a)
    cvs = list_cvs(kb, posting)
    assert [(c.id, c.version, c.parent_cv_id) for c in cvs] == [(a, 1, None), (b, 2, a)]


def test_versions_are_counted_per_posting(kb: sa.Engine, propose: Any) -> None:
    first_posting = _setup(kb, propose)
    page = FetchedPage("https://j.test/2", "https://j.test/2", "J", "t", "static")
    other = persist_posting(kb, page, JobAnalysis()).id
    _save(kb, first_posting)
    assert get_cv(kb, _save(kb, other)).version == 1  # type: ignore[union-attr]


def test_a_parent_from_another_posting_is_refused(kb: sa.Engine, propose: Any) -> None:
    posting = _setup(kb, propose)
    page = FetchedPage("https://j.test/2", "https://j.test/2", "J", "t", "static")
    other = persist_posting(kb, page, JobAnalysis()).id
    with pytest.raises(WrongPostingError):
        _save(kb, other, _save(kb, posting))


def test_a_lineage_through_a_missing_ancestor_or_a_loop_is_an_error(
    kb: sa.Engine, propose: Any
) -> None:
    posting = _setup(kb, propose)
    a = _save(kb, posting)
    b = _save(kb, posting, a)
    with pytest.raises(LineageError, match="missing"):
        lineage(kb, 999)
    with kb.begin() as conn:  # a tampered database: the root now points at its descendant
        conn.execute(sa.update(schema.cv).where(schema.cv.c.id == a).values(parent_cv_id=b))
    with pytest.raises(LineageError, match="never ends"):
        lineage(kb, b)
