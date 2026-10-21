"""FR-36: suggested values come only from the selected CV, and are never invented."""

from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.cv.store import StoredClaim, StoredCv, save_cv
from cvforge.forms.analyze import FormField
from cvforge.forms.options import suggest_values
from cvforge.forms.store import create_session, get_session
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, CvStatus, FillStatus, GenerationMode

TODAY = date(2026, 10, 21)


def _claim(id: int, section: str, slot: ClaimSlot, text: str) -> StoredClaim:
    basis = ClaimBasis.PERIOD if slot is ClaimSlot.PERIOD else ClaimBasis.NAME
    return StoredClaim(id, section, 0, slot, 0, basis, text, 1, 1, None)


def _cv(*claims: StoredClaim) -> StoredCv:
    return StoredCv(
        1, 1, 1, None, None, GenerationMode.AUTOMATIC, CvStatus.DRAFT, datetime(2026, 1, 1),
        None, None, None, claims,
    )  # fmt: skip


def _field(
    label: str, kind: str = "text", options: tuple[str, ...] = (), sensitive: bool = False
) -> FormField:
    return FormField("f1", label, True, kind, False, None, options, "#x", sensitive)


def _period(id: int, text: str) -> StoredClaim:
    return _claim(id, "Experience", ClaimSlot.PERIOD, text)


def test_years_of_experience_is_counted_from_the_cvs_role_periods() -> None:
    cv = _cv(_period(10, "2018-01 to 2021-01"), _period(11, "from 2023-01"))
    (s,) = suggest_values([_field("Years of experience")], cv, TODAY)
    assert s.value == "6" and s.claim_ids == (10, 11)


def test_overlapping_roles_count_once_and_unreadable_periods_are_skipped() -> None:
    cv = _cv(_period(1, "2020-01 to 2022-01"), _period(2, "2021-01 to 2023-01"), _period(3, "n/a"))
    (s,) = suggest_values([_field("Experience (years)")], cv, TODAY)
    assert s.value == "3"


def test_changing_the_cv_changes_the_default() -> None:
    short, long = _cv(_period(1, "2025-01 to 2026-01")), _cv(_period(2, "2016-01 to 2026-01"))
    field = [_field("Years of experience", "number")]
    assert suggest_values(field, short, TODAY)[0].value == "1"
    assert suggest_values(field, long, TODAY)[0].value == "10"


def test_a_select_gets_only_an_option_it_actually_offers() -> None:
    cv = _cv(_period(1, "2021-01 to 2026-01"))
    offered = _field("Years of experience", "select", ("1", "5", "10"))
    absent = _field("Years of experience", "select", ("0-2", "3-5"))
    assert suggest_values([offered], cv, TODAY)[0].value == "5"
    missing = suggest_values([absent], cv, TODAY)[0]
    assert missing.value is None and "no option" in missing.reason


def test_no_dated_role_means_no_years_default() -> None:
    (s,) = suggest_values([_field("Years of experience")], _cv(), TODAY)
    assert s.value is None and s.claim_ids == ()


def test_skills_are_the_cvs_skill_bullets() -> None:
    cv = _cv(
        _claim(1, "Skills", ClaimSlot.BULLET, "Python"),
        _claim(2, "Skills", ClaimSlot.BULLET, "Rust"),
        _claim(3, "Experience", ClaimSlot.BULLET, "Shipped a thing"),
    )
    (s,) = suggest_values([_field("Key skills", "textarea")], cv, TODAY)
    assert s.value == "Python, Rust" and s.claim_ids == (1, 2)
    (none,) = suggest_values([_field("Key skills")], _cv(), TODAY)
    assert none.value is None


def test_a_field_no_fact_answers_is_flagged_not_filled() -> None:
    cv = _cv(_period(1, "2020-01 to 2022-01"))
    (s,) = suggest_values([_field("Favourite colour")], cv, TODAY)
    assert s.value is None and "manually" in s.reason
    (file,) = suggest_values([_field("Years of experience", "file")], cv, TODAY)
    assert file.value is None


def test_a_password_is_never_suggested() -> None:
    (s,) = suggest_values([_field("Password", "password", sensitive=True)], _cv(), TODAY)
    assert s.value is None and "never suggested" in s.reason


def test_a_session_stores_suggestions_unconfirmed(kb: sa.Engine, propose: Any) -> None:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = save_cv(kb, posting, generate_cv(kb, posting))
    fields = [_field("Years of experience"), _field("Favourite colour")]
    fields[1] = FormField("f2", "Favourite colour", True, "text", False, None, (), "#y", False)
    suggestions = suggest_values(fields, _cv(_period(1, "2020-01 to 2022-01")), TODAY)

    session_id = create_session(kb, cv_id=cv, url="https://x.test/apply", fields=fields,
                                suggestions=suggestions)  # fmt: skip

    stored = get_session(kb, session_id)
    assert stored is not None and stored.status is FillStatus.ANALYZED and stored.cv_id == cv
    assert [f["suggested"] for f in stored.fields] == ["2", None]
    assert not any(f["confirmed"] or f["confirmed_value"] for f in stored.fields)
    assert get_session(kb, session_id + 1) is None
