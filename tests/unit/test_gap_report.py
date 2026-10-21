"""FR-23: the gap report lists exactly the undocumented and gap requirements."""

from typing import Any

import sqlalchemy as sa

from cvforge.jobs.store import get_posting, persist_posting
from cvforge.kb import apply
from cvforge.kb.vocab import MatchVerdict
from cvforge.llm.schemas import JobAnalysis
from cvforge.match.evidence import gap_report
from cvforge.match.store import replace_matches
from cvforge.match.verdicts import match_posting
from cvforge.web.fetch import FetchedPage


def _setup(kb: sa.Engine, propose: Any, skills: list[str]) -> int:
    ids = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
            {"op_type": "create_entity", "kind": "skill", "name": "Haskell"},
            {"op_type": "create_entity", "kind": "project", "name": "Parser"},
            accept=True,
        ),
    ).entity_ids
    apply.commit_proposal(
        kb,
        propose(
            {"op_type": "add_edge", "src": ids[0], "rel": "used_in", "dst": ids[2]}, accept=True
        ),
    )
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(kb, page, JobAnalysis(required_skills=skills)).id
    results = match_posting(kb, posting)
    assert results is not None
    replace_matches(kb, posting, results)
    return posting


def _report(kb: sa.Engine, posting: int) -> list[Any]:
    stored = get_posting(kb, posting)
    assert stored is not None
    return gap_report(kb, stored)


def test_the_report_is_exactly_the_undocumented_and_gap_requirements(
    kb: sa.Engine, propose: Any
) -> None:
    posting = _setup(kb, propose, ["Rust", "Haskell", "Fortran"])
    report = _report(kb, posting)

    assert [(g.verdict) for g in report] == [MatchVerdict.UNDOCUMENTED, MatchVerdict.GAP]
    stored = get_posting(kb, posting)
    assert stored is not None
    texts = {r.id: r.text for r in stored.requirements}
    assert [texts[g.requirement_id] for g in report] == ["Haskell", "Fortran"]


def test_a_fully_backed_posting_has_an_empty_report_not_an_error(
    kb: sa.Engine, propose: Any
) -> None:
    assert _report(kb, _setup(kb, propose, ["Rust"])) == []


def test_an_unmatched_posting_has_an_empty_report(kb: sa.Engine, propose: Any) -> None:
    page = FetchedPage("https://j.test/2", "https://j.test/2", "J", "t", "static")
    posting = persist_posting(kb, page, JobAnalysis(required_skills=["Rust"])).id
    assert _report(kb, posting) == []


def test_the_report_is_stable_across_runs_on_unchanged_data(kb: sa.Engine, propose: Any) -> None:
    posting = _setup(kb, propose, ["Rust", "Haskell", "Fortran"])
    first = _report(kb, posting)
    results = match_posting(kb, posting)
    assert results is not None
    replace_matches(kb, posting, results)
    assert _report(kb, posting) == first
