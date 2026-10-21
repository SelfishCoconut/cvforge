"""FR-22: every verdict names the entities and resolvable evidence behind it."""

from typing import Any

import sqlalchemy as sa

from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, queries
from cvforge.llm.schemas import JobAnalysis
from cvforge.match.evidence import detailed_matches
from cvforge.match.store import list_matches, replace_matches
from cvforge.match.verdicts import match_posting
from cvforge.web.fetch import FetchedPage


def _commit(kb: sa.Engine, propose: Any, *payloads: dict[str, Any]) -> dict[int, int]:
    return apply.commit_proposal(kb, propose(*payloads, accept=True)).entity_ids


def _matched(kb: sa.Engine, propose: Any, *skills: str) -> tuple[int, int]:
    """A posting asking for `skills`, matched against a KB where Rust is used; (posting, rust)."""
    ids = _commit(
        kb,
        propose,
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
        {"op_type": "create_entity", "kind": "project", "name": "Parser"},
    )
    _commit(kb, propose, {"op_type": "add_edge", "src": ids[0], "rel": "used_in", "dst": ids[1]})
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(kb, page, JobAnalysis(required_skills=list(skills))).id
    results = match_posting(kb, posting)
    assert results is not None
    replace_matches(kb, posting, results)
    return posting, ids[0]


def test_a_satisfied_match_cites_its_entity_and_resolvable_evidence(
    kb: sa.Engine, propose: Any
) -> None:
    posting, rust = _matched(kb, propose, "Rust")
    (detail,) = detailed_matches(kb, list_matches(kb, posting))

    (support,) = detail.support
    assert support.entity_id == rust and not support.archived
    assert support.evidence, "a backing entity always has at least one cited span"
    for span in support.evidence:
        assert span.locator and span.excerpt and span.source_kind


def test_every_cited_entity_is_fetchable(kb: sa.Engine, propose: Any) -> None:
    posting, _ = _matched(kb, propose, "Rust")
    (detail,) = detailed_matches(kb, list_matches(kb, posting))
    with kb.connect() as conn:
        assert all(queries.get_entity(conn, s.entity_id) for s in detail.support)


def test_a_gap_cites_no_entity(kb: sa.Engine, propose: Any) -> None:
    posting, _ = _matched(kb, propose, "Fortran")
    (detail,) = detailed_matches(kb, list_matches(kb, posting))
    assert detail.support == () and detail.match.support == ()


def test_a_backing_entity_archived_since_the_match_is_flagged(kb: sa.Engine, propose: Any) -> None:
    posting, rust = _matched(kb, propose, "Rust")
    apply.commit_proposal(
        kb, propose({"op_type": "set_state", "entity": rust, "state": "archived"}, accept=True)
    )

    (detail,) = detailed_matches(kb, list_matches(kb, posting))

    assert detail.support[0].archived and detail.support[0].state.value == "archived"


def test_a_vanished_entity_is_dropped_from_support_rather_than_cited(
    kb: sa.Engine, propose: Any
) -> None:
    posting, rust = _matched(kb, propose, "Rust")
    stored = list_matches(kb, posting)
    ghost = type(stored[0])(
        stored[0].id,
        stored[0].requirement_id,
        stored[0].verdict,
        stored[0].score,
        stored[0].rationale,
        (rust, 9999),
        stored[0].computed_at,
    )
    (detail,) = detailed_matches(kb, [ghost])
    assert [s.entity_id for s in detail.support] == [rust]
