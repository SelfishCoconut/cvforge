"""FR-24 / FR-25: an unsupported claim is rejected at write time and caught by validation."""

from dataclasses import replace
from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.cv.store import UnsupportedClaimError, get_cv, save_cv
from cvforge.cv.validate import validate_cv
from cvforge.kb import apply, schema


def _saved(kb: sa.Engine, propose: Any) -> tuple[int, Any]:
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    return save_cv(kb, posting, generate_cv(kb, posting)), profile


def _cv(kb: sa.Engine, cv_id: int) -> Any:
    cv = get_cv(kb, cv_id)
    assert cv is not None
    return cv


def test_a_freshly_generated_cv_validates(kb: sa.Engine, propose: Any) -> None:
    cv_id, _ = _saved(kb, propose)
    assert validate_cv(kb, _cv(kb, cv_id)) == []


def test_a_claim_without_a_supporting_assertion_cannot_be_stored(
    kb: sa.Engine, propose: Any
) -> None:
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    claims = generate_cv(kb, posting)
    forged = replace(claims[0], assertion_id=999_999)
    with pytest.raises(UnsupportedClaimError):
        save_cv(kb, posting, [forged])
    other = replace(claims[0], entity_id=profile.python)  # an assertion about a different entity
    with pytest.raises(UnsupportedClaimError):
        save_cv(kb, posting, [other])
    with kb.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(schema.cv)).scalar() == 0


def test_the_database_rejects_a_claim_row_with_a_null_assertion(
    kb: sa.Engine, propose: Any
) -> None:
    cv_id, profile = _saved(kb, propose)
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.cv_claim).values(
                cv_id=cv_id,
                section="Skills",
                item_index=9,
                slot="bullet",
                position=0,
                basis="name",
                text="Invented",
                entity_id=profile.rust,
                assertion_id=None,
            )
        )


def test_a_claim_whose_text_was_altered_is_flagged(kb: sa.Engine, propose: Any) -> None:
    cv_id, _ = _saved(kb, propose)
    with kb.begin() as conn:
        conn.execute(
            sa.update(schema.cv_claim)
            .where(schema.cv_claim.c.text == "Rust")
            .values(text="Rust expert")
        )
    issues = validate_cv(kb, _cv(kb, cv_id))
    assert [i.code for i in issues] == ["text_mismatch"]


def test_a_claim_pointing_at_another_entitys_assertion_is_unsupported(
    kb: sa.Engine, propose: Any
) -> None:
    cv_id, profile = _saved(kb, propose)
    with kb.connect() as conn:
        python_assertion = conn.execute(
            sa.select(sa.func.min(schema.assertion.c.id)).where(
                schema.assertion.c.target_id == profile.python,
                schema.assertion.c.target_kind == "entity",
            )
        ).scalar_one()
    with kb.begin() as conn:
        conn.execute(
            sa.update(schema.cv_claim)
            .where(schema.cv_claim.c.text == "Rust")
            .values(assertion_id=python_assertion)
        )
    assert [i.code for i in validate_cv(kb, _cv(kb, cv_id))] == ["unsupported"]


def test_a_claim_on_an_entity_archived_since_is_flagged(kb: sa.Engine, propose: Any) -> None:
    cv_id, profile = _saved(kb, propose)
    apply.commit_proposal(
        kb,
        propose({"op_type": "set_state", "entity": profile.rust, "state": "archived"}, accept=True),
    )
    issues = validate_cv(kb, _cv(kb, cv_id))
    assert "inactive_entity" in {i.code for i in issues}


def test_saving_for_an_unknown_parent_is_a_not_found(kb: sa.Engine, propose: Any) -> None:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    with pytest.raises(apply.NotFoundError):
        save_cv(kb, posting, [], parent_cv_id=42)
