"""Copy a stored fact into the exact string a CV claim carries (FR-24, FR-25).

Generation and validation both use this, so the text a claim holds is, by construction,
the text recomputable from the knowledge base. A fact with no assertion stating it yields
nothing: it cannot become a claim.
"""

from datetime import date
from typing import Any

import sqlalchemy as sa

from cvforge.kb import queries
from cvforge.kb.vocab import ClaimBasis

_START_FIELDS = ("started_at", "issued_at", "occurred_at")
_SINGLE_DATE_FIELDS = frozenset({"issued_at", "occurred_at"})


def _month(value: Any) -> str:
    return value.strftime("%Y-%m") if isinstance(value, date) else str(value)[:7]


def _period(attributes: dict[str, Any]) -> tuple[str, str] | None:
    """The period text and the attribute field that states its start, or None."""
    for field in _START_FIELDS:
        start = attributes.get(field)
        if start is None:
            continue
        end = attributes.get("ended_at")
        if field in _SINGLE_DATE_FIELDS:
            return _month(start), field
        if end is None:
            return f"from {_month(start)}", field
        return f"{_month(start)} to {_month(end)}", field
    return None


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _stating(conn: sa.Connection, entity_id: int, field: str, current: Any) -> int | None:
    """The assertion that states `field` of the entity *with the entity's current value*.

    A claim is only as good as the assertion whose recorded value is the text it carries: an
    assertion of the same field with a different value (a stale name, say) does not count.
    """
    assertion_id = queries.entity_assertion_id(conn, entity_id, field)
    assertion = None if assertion_id is None else queries.get_assertion(conn, assertion_id)
    if assertion is None or _iso(assertion.value) != _iso(current):
        return None
    return assertion.id


def claim_source(conn: sa.Connection, entity_id: int, basis: ClaimBasis) -> tuple[str, int] | None:
    """The text a claim of `basis` about `entity_id` must carry, and the assertion behind it.

    The assertion's recorded value is the fact itself: for a name, the assertion of field
    `name` whose value is the current name; for a period, the assertion of the start date (and,
    when the entity has an end date, the assertion of that too).

    Args:
        conn: An open connection.
        entity_id: The entity.
        basis: Which fact to copy.

    Returns:
        (text, assertion id), or None if the entity lacks that fact or no assertion states it.
    """
    record = queries.get_entity(conn, entity_id)
    if record is None:
        return None
    if basis is ClaimBasis.NAME:
        assertion = _stating(conn, entity_id, "name", record.name)
        return None if assertion is None else (record.name, assertion)
    if basis is ClaimBasis.SUMMARY:
        if not record.summary:
            return None
        assertion = _stating(conn, entity_id, "summary", record.summary)
        return None if assertion is None else (record.summary, assertion)
    return _period_source(conn, entity_id, record)


def _period_source(
    conn: sa.Connection, entity_id: int, record: queries.EntityRecord
) -> tuple[str, int] | None:
    """The period text and its start-date assertion; an end date shown needs its own assertion."""
    period = _period(record.attributes)
    if period is None:
        return None
    text, field = period
    start = _stating(conn, entity_id, field, record.attributes[field])
    end = record.attributes.get("ended_at")
    if start is None or (end is not None and _stating(conn, entity_id, "ended_at", end) is None):
        return None
    return text, start
