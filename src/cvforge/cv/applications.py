"""Track which CV was sent for which posting, and when (FR-28).

Registered writer (ADR-0011, ADR-0026): may write `application`, nothing else. An
application ties a posting to a CV that targets that posting and has been marked final, so
a CV that never passed validation cannot be recorded as sent.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from cvforge.cv.store import get_cv
from cvforge.kb import apply, schema
from cvforge.kb.db import write_transaction
from cvforge.kb.vocab import ApplicationStatus, CvStatus


class ApplicationError(Exception):
    """An application cannot be recorded as asked."""


@dataclass(frozen=True)
class Application:
    """One recorded application.

    Attributes:
        id: The `application` row id.
        job_posting_id: The posting applied to.
        cv_id: The CV that was used.
        status: Where the application stands.
        applied_at: When it was sent, if it was.
        notes: Free notes.
    """

    id: int
    job_posting_id: int
    cv_id: int
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None


def _app(row: sa.Row[Any]) -> Application:
    return Application(
        row.id,
        row.job_posting_id,
        row.cv_id,
        ApplicationStatus(row.status),
        row.applied_at,
        row.notes,
    )


def record_application(
    engine: sa.Engine,
    posting_id: int,
    cv_id: int,
    *,
    status: ApplicationStatus = ApplicationStatus.APPLIED,
    applied_at: datetime | None = None,
    notes: str | None = None,
) -> Application:
    """Record that `cv_id` was used for `posting_id`.

    Args:
        engine: The knowledge-base engine.
        posting_id: The `job_posting` applied to.
        cv_id: The CV used; it must target that posting and be final.
        status: Where the application stands.
        applied_at: When it was sent; required once the status is beyond `planned`.
        notes: Free notes.

    Returns:
        The stored application.

    Raises:
        NotFoundError: If the CV does not exist.
        ApplicationError: If the CV targets another posting, is not final, or an applied
            status has no date.
    """
    cv = get_cv(engine, cv_id)
    if cv is None:
        raise apply.NotFoundError(f"no CV {cv_id}")
    if cv.job_posting_id != posting_id:
        raise ApplicationError(f"CV {cv_id} targets posting {cv.job_posting_id}, not {posting_id}")
    if cv.status is not CvStatus.FINAL:
        raise ApplicationError(f"CV {cv_id} is a draft; only a validated, final CV can be sent")
    if status is not ApplicationStatus.PLANNED and applied_at is None:
        raise ApplicationError(f"an application with status {status.value!r} needs applied_at")
    with write_transaction(engine) as conn:
        new_id = int(
            conn.execute(
                sa.insert(schema.application)
                .values(
                    job_posting_id=posting_id,
                    cv_id=cv_id,
                    status=status.value,
                    applied_at=applied_at,
                    notes=notes,
                )
                .returning(schema.application.c.id)
            ).scalar_one()
        )
        row = conn.execute(
            sa.select(schema.application).where(schema.application.c.id == new_id)
        ).one()
    return _app(row)


def set_application_status(
    engine: sa.Engine, application_id: int, status: ApplicationStatus
) -> Application:
    """Move an application to a new status.

    Args:
        engine: The knowledge-base engine.
        application_id: The `application` id.
        status: The new status.

    Returns:
        The updated application.

    Raises:
        NotFoundError: If there is no such application.
        ApplicationError: If the status needs a date the application lacks.
    """
    with write_transaction(engine) as conn:
        row = conn.execute(
            sa.select(schema.application).where(schema.application.c.id == application_id)
        ).first()
        if row is None:
            raise apply.NotFoundError(f"no application {application_id}")
        if status is not ApplicationStatus.PLANNED and row.applied_at is None:
            raise ApplicationError(f"an application with status {status.value!r} needs applied_at")
        conn.execute(
            sa.update(schema.application)
            .where(schema.application.c.id == application_id)
            .values(status=status.value)
        )
        row = conn.execute(
            sa.select(schema.application).where(schema.application.c.id == application_id)
        ).one()
    return _app(row)


def list_applications(
    engine: sa.Engine, *, cv_id: int | None = None, posting_id: int | None = None
) -> list[Application]:
    """List applications, optionally for one CV or one posting.

    Args:
        engine: The knowledge-base engine.
        cv_id: Only applications that used this CV.
        posting_id: Only applications to this posting.

    Returns:
        Applications ordered by id.
    """
    query = sa.select(schema.application).order_by(schema.application.c.id)
    if cv_id is not None:
        query = query.where(schema.application.c.cv_id == cv_id)
    if posting_id is not None:
        query = query.where(schema.application.c.job_posting_id == posting_id)
    with engine.connect() as conn:
        return [_app(row) for row in conn.execute(query)]
