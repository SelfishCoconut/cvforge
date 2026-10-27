"""Persist form-fill sessions: the suggestions for a form and, later, what was confirmed (FR-36).

Registered writer (ADR-0011, ADR-0030): may write `form_fill_session`, nothing else. A session
holds suggestions and confirmations, which are not knowledge, so it carries no assertion.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from cvforge.forms.analyze import FormField
from cvforge.forms.options import Suggestion
from cvforge.kb import schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import FillStatus


@dataclass(frozen=True)
class StoredSession:
    """A stored form-fill session.

    Attributes:
        id: The `form_fill_session` id.
        application_id: The application it is for, if any.
        cv_id: The CV the suggestions were drawn from.
        url: The form's page.
        fields: Each field with its suggestion and confirmation state, as stored.
        status: `analyzed` or `filled`.
        created_at: When it was created.
    """

    id: int
    application_id: int | None
    cv_id: int
    url: str
    fields: list[dict[str, Any]]
    status: FillStatus
    created_at: datetime


def _entry(field: FormField, suggestion: Suggestion) -> dict[str, Any]:
    return {
        "key": field.key,
        "label": field.label,
        "type": field.type,
        "required": field.required,
        "options": list(field.options),
        "selector": field.selector,
        "suggested": suggestion.value,
        "claim_ids": list(suggestion.claim_ids),
        "reason": suggestion.reason,
        "confirmed_value": None,
        "confirmed": False,
    }


def create_session(
    engine: sa.Engine,
    *,
    cv_id: int,
    url: str,
    fields: list[FormField],
    suggestions: list[Suggestion],
    application_id: int | None = None,
) -> int:
    """Store the analysed fields with their suggestions, all unconfirmed.

    Args:
        engine: The knowledge-base engine.
        cv_id: The CV the suggestions were drawn from.
        url: The form's page.
        fields: The analysed fields.
        suggestions: One per field, in the same order.
        application_id: The application it is for, if any.

    Returns:
        The new session id.
    """
    entries = [_entry(f, s) for f, s in zip(fields, suggestions, strict=True)]
    with write_transaction(engine) as conn:
        return int(
            conn.execute(
                sa.insert(schema.form_fill_session)
                .values(
                    application_id=application_id,
                    cv_id=cv_id,
                    url=url,
                    fields_json=json.dumps(entries),
                    status=FillStatus.ANALYZED.value,
                    created_at=utc_now(),
                )
                .returning(schema.form_fill_session.c.id)
            ).scalar_one()
        )


def get_session(engine: sa.Engine, session_id: int) -> StoredSession | None:
    """Read one session.

    Args:
        engine: The knowledge-base engine.
        session_id: The `form_fill_session` id.

    Returns:
        The session, or None if there is none.
    """
    with engine.connect() as conn:
        row = conn.execute(
            sa.select(schema.form_fill_session).where(schema.form_fill_session.c.id == session_id)
        ).first()
    if row is None:
        return None
    return StoredSession(
        row.id,
        row.application_id,
        row.cv_id,
        row.url,
        json.loads(row.fields_json),
        FillStatus(row.status),
        row.created_at,
    )


class SessionError(Exception):
    """A confirmation or fill the session's state does not allow."""


def _require_open(conn: sa.Connection, session_id: int) -> list[dict[str, Any]]:
    row = conn.execute(
        sa.select(schema.form_fill_session.c.fields_json, schema.form_fill_session.c.status).where(
            schema.form_fill_session.c.id == session_id
        )
    ).first()
    if row is None:
        raise SessionError(f"no form-fill session {session_id}")
    if row.status != FillStatus.ANALYZED.value:
        raise SessionError(f"session {session_id} was already filled")
    fields: list[dict[str, Any]] = json.loads(row.fields_json)
    return fields


def _save(conn: sa.Connection, session_id: int, fields: list[dict[str, Any]]) -> None:
    conn.execute(
        sa.update(schema.form_fill_session)
        .where(schema.form_fill_session.c.id == session_id)
        .values(fields_json=json.dumps(fields))
    )


def confirm_field(engine: sa.Engine, session_id: int, key: str, value: str) -> None:
    """Record the value the user approved for one field (the suggestion, edited or not).

    Args:
        engine: The knowledge-base engine.
        session_id: The session, which must not have been filled yet.
        key: The field's key.
        value: The approved value; for a select or radio group it must be one of the options.

    Raises:
        SessionError: If the session or field is unknown, the session was filled, the value is
            blank, the field is a password or file, or the value is not one of its options.
    """
    with write_transaction(engine) as conn:
        fields = _require_open(conn, session_id)
        field = next((f for f in fields if f["key"] == key), None)
        if field is None:
            raise SessionError(f"session {session_id} has no field {key}")
        if field["type"] in ("password", "file"):
            raise SessionError(f"a {field['type']} field is never filled")
        if not value.strip():
            raise SessionError("a confirmed value cannot be blank")
        if field["type"] in ("select", "radio") and value not in field["options"]:
            raise SessionError(f"{value!r} is not an option of {field['label']!r}")
        field["confirmed_value"], field["confirmed"] = value, True
        _save(conn, session_id, fields)


def unconfirm_field(engine: sa.Engine, session_id: int, key: str) -> None:
    """Withdraw a confirmation; the field is left untouched by the next fill.

    Args:
        engine: The knowledge-base engine.
        session_id: The session, which must not have been filled yet.
        key: The field's key.

    Raises:
        SessionError: If the session or field is unknown or the session was filled.
    """
    with write_transaction(engine) as conn:
        fields = _require_open(conn, session_id)
        field = next((f for f in fields if f["key"] == key), None)
        if field is None:
            raise SessionError(f"session {session_id} has no field {key}")
        field["confirmed_value"], field["confirmed"] = None, False
        _save(conn, session_id, fields)


def mark_filled(engine: sa.Engine, session_id: int) -> None:
    """Claim the session for filling, so it cannot be filled twice.

    Call it before the browser opens; the check and the update share one write transaction.

    Args:
        engine: The knowledge-base engine.
        session_id: The session.

    Raises:
        SessionError: If the session is unknown or was already filled.
    """
    with write_transaction(engine) as conn:
        _require_open(conn, session_id)
        conn.execute(
            sa.update(schema.form_fill_session)
            .where(schema.form_fill_session.c.id == session_id)
            .values(status=FillStatus.FILLED.value)
        )


def release_fill(engine: sa.Engine, session_id: int) -> None:
    """Give back a claim whose fill never started, so the user can retry.

    Args:
        engine: The knowledge-base engine.
        session_id: The session.
    """
    with write_transaction(engine) as conn:
        conn.execute(
            sa.update(schema.form_fill_session)
            .where(schema.form_fill_session.c.id == session_id)
            .values(status=FillStatus.ANALYZED.value)
        )
