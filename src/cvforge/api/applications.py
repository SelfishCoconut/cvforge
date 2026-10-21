"""Record which CV was used for which application (FR-28)."""

from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from cvforge.api.errors import engine
from cvforge.cv.applications import (
    Application,
    ApplicationError,
    list_applications,
    record_application,
    set_application_status,
)
from cvforge.kb.vocab import ApplicationStatus

router = APIRouter(tags=["applications"])
Engine = Annotated[sa.Engine, Depends(engine)]


class ApplicationView(BaseModel):
    """A recorded application.

    Attributes:
        id: The application id.
        job_posting_id: The posting applied to.
        cv_id: The CV used.
        status: Where it stands.
        applied_at: When it was sent, if it was.
        notes: Free notes.
    """

    id: int
    job_posting_id: int
    cv_id: int
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None


class ApplicationRequest(BaseModel):
    """An application to record.

    Attributes:
        job_posting_id: The posting applied to.
        cv_id: The CV used; it must target that posting and be final.
        status: Where it stands (default `applied`).
        applied_at: When it was sent; required unless the status is `planned`.
        notes: Free notes.
    """

    job_posting_id: int
    cv_id: int
    status: ApplicationStatus = ApplicationStatus.APPLIED
    applied_at: datetime | None = None
    notes: str | None = None


class StatusRequest(BaseModel):
    """A new status.

    Attributes:
        status: The status to move to.
    """

    status: ApplicationStatus


def _view(application: Application) -> ApplicationView:
    return ApplicationView(
        id=application.id,
        job_posting_id=application.job_posting_id,
        cv_id=application.cv_id,
        status=application.status,
        applied_at=application.applied_at,
        notes=application.notes,
    )


@router.post("/applications", status_code=201)
def create_application(body: ApplicationRequest, db: Engine) -> ApplicationView:
    """Record that a final CV was used for a posting.

    Args:
        body: The application.
        db: The knowledge-base engine.

    Returns:
        The stored application.

    Raises:
        NotFoundError: If the CV does not exist (404).
        HTTPException: 422 if the CV targets another posting, is not final, or the status
            needs a date.
    """
    try:
        return _view(
            record_application(
                db,
                body.job_posting_id,
                body.cv_id,
                status=body.status,
                applied_at=body.applied_at,
                notes=body.notes,
            )
        )
    except ApplicationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/applications")
def read_applications(
    db: Engine, cv_id: int | None = None, job_posting_id: int | None = None
) -> list[ApplicationView]:
    """List applications, optionally those that used one CV or went to one posting.

    Args:
        db: The knowledge-base engine.
        cv_id: Only applications that used this CV.
        job_posting_id: Only applications to this posting.

    Returns:
        The applications.
    """
    return [_view(a) for a in list_applications(db, cv_id=cv_id, posting_id=job_posting_id)]


@router.post("/applications/{application_id}/status")
def change_status(
    application_id: int, body: StatusRequest, db: Engine, response: Response
) -> ApplicationView:
    """Move an application to a new status.

    Args:
        application_id: The application id.
        body: The new status.
        db: The knowledge-base engine.
        response: The response, unused on success.

    Returns:
        The updated application.

    Raises:
        NotFoundError: If there is no such application (404).
        HTTPException: 422 if the status needs a date the application lacks.
    """
    try:
        return _view(set_application_status(db, application_id, body.status))
    except ApplicationError as exc:
        raise HTTPException(422, str(exc)) from exc
