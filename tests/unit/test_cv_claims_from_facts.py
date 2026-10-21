"""FR-24 / NFR-05: a CV is built from stored facts only; nothing unsupported appears."""

from typing import Any

import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.cv.model import ClaimDraft
from cvforge.kb import apply, queries, schema
from cvforge.kb.vocab import ClaimSlot


def _texts(claims: list[ClaimDraft]) -> list[str]:
    return [c.text for c in claims]


def test_every_claim_names_an_entity_and_an_assertion_about_it(kb: sa.Engine, propose: Any) -> None:
    build_profile(kb, propose)
    claims = generate_cv(kb, matched_posting(kb, "Rust"))

    assert claims
    with kb.connect() as conn:
        for claim in claims:
            assertion = queries.get_assertion(conn, claim.assertion_id)
            assert assertion is not None
            assert (assertion.target_kind, assertion.target_id) == ("entity", claim.entity_id)


def test_a_satisfied_skill_pulls_in_its_role_organization_project_and_period(
    kb: sa.Engine, propose: Any
) -> None:
    build_profile(kb, propose)
    claims = generate_cv(kb, matched_posting(kb, "Rust"))

    by_section = {s: [c for c in claims if c.section == s] for s in {c.section for c in claims}}
    assert _texts(by_section["Skills"]) == ["Rust"]
    experience = by_section["Experience"]
    assert [(c.slot, c.text) for c in experience] == [
        (ClaimSlot.HEADER, "Backend Engineer"),
        (ClaimSlot.SUBHEADER, "Acme Logistics"),
        (ClaimSlot.PERIOD, "2019-01 to 2022-06"),
        (ClaimSlot.BULLET, "Built data services"),
        (ClaimSlot.BULLET, "Parsed two gigabytes per second"),
    ]
    assert [c.text for c in by_section["Education"]] == [
        "BSc Computer Science",
        "2014-09 to 2018-06",
    ]
    assert "2021-03" in _texts(by_section["Certifications"])


def test_requirements_that_are_gap_or_undocumented_never_appear(
    kb: sa.Engine, propose: Any
) -> None:
    build_profile(kb, propose)
    claims = generate_cv(kb, matched_posting(kb, "Rust", "Haskell", "Python", "Fortran"))
    text = " ".join(_texts(claims))

    for absent in ("Haskell", "Python", "Fortran"):
        assert absent not in text
    assert "Rust" in text


def test_a_posting_nothing_backs_yields_only_unconditional_sections(
    kb: sa.Engine, propose: Any
) -> None:
    build_profile(kb, propose)
    claims = generate_cv(kb, matched_posting(kb, "Fortran"))
    assert {c.section for c in claims} == {"Education", "Certifications"}


def test_an_entity_archived_after_matching_drops_out(kb: sa.Engine, propose: Any) -> None:
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    apply.commit_proposal(
        kb,
        propose({"op_type": "set_state", "entity": profile.rust, "state": "archived"}, accept=True),
    )
    claims = generate_cv(kb, posting)
    assert "Rust" not in _texts(claims) and "Experience" not in {c.section for c in claims}


def test_generation_writes_no_knowledge(kb: sa.Engine, propose: Any) -> None:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    generate_cv(kb, posting)
    with kb.connect() as conn:
        after = queries.table_counts(conn)
    assert after == before


def test_a_fact_without_an_assertion_is_not_claimed(kb: sa.Engine, propose: Any) -> None:
    """A summary whose assertion is gone cannot become a bullet."""
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    with kb.begin() as conn:
        conn.execute(
            sa.delete(schema.assertion).where(
                schema.assertion.c.target_id == profile.project,
                schema.assertion.c.field == "summary",
            )
        )
    assert "Parsed two gigabytes per second" not in _texts(generate_cv(kb, posting))


def test_period_formats_for_open_ended_and_single_date_facts() -> None:
    from cvforge.cv.facts import _period

    assert _period({"started_at": "2020-05-01"}) == ("from 2020-05", "started_at")
    assert _period({"issued_at": "2021-03-09"}) == ("2021-03", "issued_at")
    assert _period({"started_at": "2019-01-01", "ended_at": "2020-02-02"}) == (
        "2019-01 to 2020-02",
        "started_at",
    )
    assert _period({}) is None


def test_a_missing_entity_or_a_fact_it_lacks_yields_no_claim_source(
    kb: sa.Engine, propose: Any
) -> None:
    from cvforge.cv.facts import claim_source
    from cvforge.kb.vocab import ClaimBasis

    profile = build_profile(kb, propose)
    with kb.connect() as conn:
        assert claim_source(conn, 9999, ClaimBasis.NAME) is None
        assert claim_source(conn, profile.rust, ClaimBasis.PERIOD) is None  # a skill has no dates
        assert claim_source(conn, profile.rust, ClaimBasis.SUMMARY) is None  # and no summary
