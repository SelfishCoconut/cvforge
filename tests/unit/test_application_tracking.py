"""FR-28: an application links a posting and a final CV, with a closed status set."""

from datetime import datetime
from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.applications import (
    ApplicationError,
    list_applications,
    record_application,
    set_application_status,
)
from cvforge.cv.generate import generate_cv
from cvforge.cv.store import save_cv, set_status
from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, schema
from cvforge.kb.vocab import ApplicationStatus, CvStatus
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

WHEN = datetime(2026, 10, 21, 9, 30)


def _final_cv(kb: sa.Engine, propose: Any) -> tuple[int, int]:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = save_cv(kb, posting, generate_cv(kb, posting))
    set_status(kb, cv, CvStatus.FINAL)
    return posting, cv


def test_recording_links_the_posting_the_cv_and_the_time(kb: sa.Engine, propose: Any) -> None:
    posting, cv = _final_cv(kb, propose)
    application = record_application(kb, posting, cv, applied_at=WHEN, notes="via referral")
    assert (application.job_posting_id, application.cv_id) == (posting, cv)
    assert (application.applied_at, application.status) == (WHEN, ApplicationStatus.APPLIED)


def test_a_cvs_usages_are_every_application_it_was_used_for(kb: sa.Engine, propose: Any) -> None:
    posting, cv = _final_cv(kb, propose)
    first = record_application(kb, posting, cv, applied_at=WHEN)
    second = record_application(kb, posting, cv, applied_at=WHEN)
    assert [a.id for a in list_applications(kb, cv_id=cv)] == [first.id, second.id]
    assert list_applications(kb, cv_id=cv + 1) == []
    assert len(list_applications(kb, posting_id=posting)) == 2


def test_a_nonexistent_cv_is_rejected(kb: sa.Engine, propose: Any) -> None:
    posting, _ = _final_cv(kb, propose)
    with pytest.raises(apply.NotFoundError):
        record_application(kb, posting, 999, applied_at=WHEN)
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:  # and the database agrees
        conn.execute(
            sa.insert(schema.application).values(
                job_posting_id=posting, cv_id=999, status="applied"
            )
        )


def test_status_is_a_closed_set(kb: sa.Engine, propose: Any) -> None:
    posting, cv = _final_cv(kb, propose)
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.application).values(job_posting_id=posting, cv_id=cv, status="ghosted")
        )


def test_a_draft_cv_or_one_for_another_posting_cannot_be_recorded(
    kb: sa.Engine, propose: Any
) -> None:
    posting, cv = _final_cv(kb, propose)
    draft = save_cv(kb, posting, generate_cv(kb, posting))
    with pytest.raises(ApplicationError, match="draft"):
        record_application(kb, posting, draft, applied_at=WHEN)
    page = FetchedPage("https://j.test/2", "https://j.test/2", "J", "t", "static")
    other = persist_posting(kb, page, JobAnalysis()).id
    with pytest.raises(ApplicationError, match="targets posting"):
        record_application(kb, other, cv, applied_at=WHEN)


def test_an_applied_status_needs_a_date_but_a_plan_does_not(kb: sa.Engine, propose: Any) -> None:
    posting, cv = _final_cv(kb, propose)
    with pytest.raises(ApplicationError, match="needs applied_at"):
        record_application(kb, posting, cv)
    planned = record_application(kb, posting, cv, status=ApplicationStatus.PLANNED)
    assert planned.applied_at is None
    with pytest.raises(ApplicationError, match="needs applied_at"):
        set_application_status(kb, planned.id, ApplicationStatus.APPLIED)


def test_status_can_move_forward_and_an_unknown_application_is_not_found(
    kb: sa.Engine, propose: Any
) -> None:
    posting, cv = _final_cv(kb, propose)
    application = record_application(kb, posting, cv, applied_at=WHEN)
    moved = set_application_status(kb, application.id, ApplicationStatus.INTERVIEWING)
    assert moved.status is ApplicationStatus.INTERVIEWING
    with pytest.raises(apply.NotFoundError):
        set_application_status(kb, 999, ApplicationStatus.OFFER)
