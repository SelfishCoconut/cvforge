"""Application-form autofill: analyse, suggest, confirm, fill (FR-35, FR-36, FR-37).

The page is fetched with the same safeguards as a job posting (public http(s) only, size and
time caps, a browser fallback for JavaScript-built forms) and read for structure only. Suggestions
come from the selected CV, a value is written only after it was confirmed here, and nothing is
ever submitted.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cvforge.api.errors import engine
from cvforge.cv.store import get_cv
from cvforge.forms.analyze import FormField, analyze_form
from cvforge.forms.fill import FillReport, fill_session
from cvforge.forms.options import suggest_values
from cvforge.forms.store import (
    SessionError,
    StoredSession,
    confirm_field,
    create_session,
    get_session,
    mark_filled,
    unconfirm_field,
)
from cvforge.kb import apply
from cvforge.kb.vocab import FillStatus
from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import FetchError, fetch_html

router = APIRouter(tags=["forms"])
Engine = Annotated[sa.Engine, Depends(engine)]
HtmlFetcher = Callable[[str], str]
FormFiller = Callable[[StoredSession], FillReport]


def default_html_fetcher(url: str) -> str:
    """Fetch `url`'s HTML statically, rendering in a browser if the page holds no form.

    Args:
        url: The form page URL.

    Returns:
        The HTML.
    """
    return fetch_html(url, browser=PlaywrightFetcher())


def make_form_filler(data_dir: Path) -> FormFiller:
    """Build the filler that opens a visible browser on the dedicated profile under `data/`.

    Args:
        data_dir: The private data directory.

    Returns:
        A function that fills a session's confirmed fields and returns what it did.
    """
    return lambda session: fill_session(session, data_dir / "browser-profile")


def _fetcher(request: Request) -> HtmlFetcher:
    result: HtmlFetcher = request.app.state.form_html_fetcher
    return result


def _filler(request: Request) -> FormFiller:
    result: FormFiller = request.app.state.form_filler
    return result


Fetcher = Annotated[HtmlFetcher, Depends(_fetcher)]
Filler = Annotated[FormFiller, Depends(_filler)]


class AnalyzeRequest(BaseModel):
    """A form page to analyse.

    Attributes:
        url: The page's http(s) URL.
    """

    url: str = Field(min_length=1, max_length=2048)


class FieldView(BaseModel):
    """One field of a form.

    Attributes:
        key: A stable identifier within the form.
        label: What the page calls it (`Field N` when it gives no label).
        labelled: False when the label is a placeholder.
        type: The inferred type.
        required: Whether the page marks it required.
        name: The `name` attribute, if any.
        options: The choices of a select or radio group.
        sensitive: True for a password field, which is never suggested or filled.
    """

    key: str
    label: str
    labelled: bool
    type: str
    required: bool
    name: str | None
    options: list[str]
    sensitive: bool


def field_view(item: FormField) -> FieldView:
    """Describe a field for a response (the page-specific selector stays server-side).

    Args:
        item: The analysed field.

    Returns:
        The view.
    """
    return FieldView(
        key=item.key,
        label=item.label,
        labelled=item.labelled,
        type=item.type,
        required=item.required,
        name=item.name,
        options=list(item.options),
        sensitive=item.sensitive,
    )


@router.post("/forms/analyze")
def analyze(body: AnalyzeRequest, fetch: Fetcher) -> list[FieldView]:
    """List the fields of the application form at a URL.

    Args:
        body: The page URL.
        fetch: Fetches the page's HTML.

    Returns:
        The fields in document order; empty if the page has no form.

    Raises:
        HTTPException: 422 if the page cannot be fetched or is refused.
    """
    try:
        html = fetch(body.url)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    return [field_view(f) for f in analyze_form(html)]


class SessionRequest(BaseModel):
    """Which form to analyse and whose CV to draw suggestions from.

    Attributes:
        url: The application form's page.
        cv_id: The CV whose claims supply the suggested values.
        application_id: The application this is for, if tracked.
    """

    url: str
    cv_id: int
    application_id: int | None = None


class SessionFieldView(BaseModel):
    """One field with its suggestion and confirmation state.

    Attributes:
        key: The field's key within the form.
        label: What the page calls it.
        type: The control type.
        required: Whether the page marks it required.
        options: The choices of a select or radio group.
        suggested: The value drawn from the CV, or None if no stored fact answers.
        claim_ids: The CV claims the suggestion came from.
        reason: Why there is, or is not, a suggestion.
        confirmed: Whether the user approved a value to fill.
        confirmed_value: The approved value.
    """

    key: str
    label: str
    type: str
    required: bool
    options: list[str]
    suggested: str | None
    claim_ids: list[int]
    reason: str
    confirmed: bool
    confirmed_value: str | None


class SessionView(BaseModel):
    """A form-fill session.

    Attributes:
        id: The session id.
        application_id: The application, if any.
        cv_id: The CV the suggestions came from.
        url: The form's page.
        status: `analyzed` or `filled`.
        fields: The fields in page order.
    """

    id: int
    application_id: int | None
    cv_id: int
    url: str
    status: FillStatus
    fields: list[SessionFieldView]


class ConfirmRequest(BaseModel):
    """The value the user approved for a field.

    Attributes:
        value: The value to fill; the suggestion as is, or the user's edit.
    """

    value: str


class FillResult(BaseModel):
    """What a fill run did.

    Attributes:
        filled: Keys of the fields written.
        skipped: Confirmed fields that were not written, with the reason.
    """

    filled: list[str]
    skipped: dict[str, str]


def _view(session: StoredSession) -> SessionView:
    return SessionView(
        id=session.id,
        application_id=session.application_id,
        cv_id=session.cv_id,
        url=session.url,
        status=session.status,
        fields=[
            SessionFieldView.model_validate({k: f[k] for k in SessionFieldView.model_fields})
            for f in session.fields
        ],
    )


def _require(db: sa.Engine, fill_id: int) -> StoredSession:
    session = get_session(db, fill_id)
    if session is None:
        raise apply.NotFoundError(f"no form-fill session {fill_id}")
    return session


@router.post("/forms/fills", status_code=201)
def start_session(body: SessionRequest, db: Engine, fetcher: Fetcher) -> SessionView:
    """Fetch a form, list its fields and suggest a value for each from the chosen CV.

    Nothing is filled and nothing is confirmed yet.

    Args:
        body: The form URL and CV.
        db: The knowledge-base engine.
        fetcher: Fetches the page's HTML.

    Returns:
        The stored session.

    Raises:
        NotFoundError: If the CV does not exist (404).
        HTTPException: 422 if the page cannot be fetched or holds no fillable form.
    """
    cv = get_cv(db, body.cv_id)
    if cv is None:
        raise apply.NotFoundError(f"no CV {body.cv_id}")
    try:
        fields = analyze_form(fetcher(body.url))
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not fields:
        raise HTTPException(422, "no fillable form was found on that page")
    fill_id = create_session(
        db,
        cv_id=cv.id,
        url=body.url,
        fields=fields,
        suggestions=suggest_values(fields, cv, date.today()),
        application_id=body.application_id,
    )
    return _view(_require(db, fill_id))


@router.get("/forms/fills/{fill_id}")
def read_session(fill_id: int, db: Engine) -> SessionView:
    """Read one session.

    Args:
        fill_id: A session id.
        db: The knowledge-base engine.

    Returns:
        The session.

    Raises:
        NotFoundError: If there is no such session (404).
    """
    return _view(_require(db, fill_id))


@router.put("/forms/fills/{fill_id}/fields/{key}")
def confirm(fill_id: int, key: str, body: ConfirmRequest, db: Engine) -> SessionView:
    """Approve the value to fill into one field.

    Args:
        fill_id: A session id.
        key: The field's key.
        body: The approved value.
        db: The knowledge-base engine.

    Returns:
        The session after the confirmation.

    Raises:
        NotFoundError: If there is no such session (404).
        HTTPException: 409 if the session was filled or the field cannot take the value.
    """
    _require(db, fill_id)
    try:
        confirm_field(db, fill_id, key, body.value)
    except SessionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _view(_require(db, fill_id))


@router.delete("/forms/fills/{fill_id}/fields/{key}")
def unconfirm(fill_id: int, key: str, db: Engine) -> SessionView:
    """Withdraw a confirmation; the field is then left untouched by the fill.

    Args:
        fill_id: A session id.
        key: The field's key.
        db: The knowledge-base engine.

    Returns:
        The session after the change.

    Raises:
        NotFoundError: If there is no such session (404).
        HTTPException: 409 if the session was filled or has no such field.
    """
    _require(db, fill_id)
    try:
        unconfirm_field(db, fill_id, key)
    except SessionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _view(_require(db, fill_id))


@router.post("/forms/fills/{fill_id}/fill")
def fill(fill_id: int, db: Engine, filler: Filler) -> FillResult:
    """Open the form in a visible browser and write the confirmed values; never submit.

    The request returns when the window is closed, so the user can review the form and submit it
    themself. A session can be filled once.

    Args:
        fill_id: A session id.
        db: The knowledge-base engine.
        filler: Runs the browser.

    Returns:
        Which fields were written and which confirmed ones were skipped.

    Raises:
        NotFoundError: If there is no such session (404).
        HTTPException: 409 if it was already filled or nothing is confirmed; 422 if the page
            cannot be opened.
    """
    session = _require(db, fill_id)
    if session.status is FillStatus.FILLED:
        raise HTTPException(409, f"session {fill_id} was already filled")
    if not any(f["confirmed"] for f in session.fields):
        raise HTTPException(409, "confirm at least one field before filling")
    try:
        report = filler(session)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    mark_filled(db, fill_id)
    return FillResult(filled=list(report.filled), skipped=dict(report.skipped))
