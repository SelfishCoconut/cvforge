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


def claim_source(conn: sa.Connection, entity_id: int, basis: ClaimBasis) -> tuple[str, int] | None:
    """The text a claim of `basis` about `entity_id` must carry, and the assertion behind it.

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
        return _required(queries.entity_assertion_id(conn, entity_id, None), record.name)
    if basis is ClaimBasis.SUMMARY:
        if not record.summary:
            return None
        return _required(queries.entity_assertion_id(conn, entity_id, "summary"), record.summary)
    period = _period(record.attributes)
    if period is None:
        return None
    text, field = period
    return _required(queries.entity_assertion_id(conn, entity_id, field), text)


def _required(assertion_id: int | None, text: str) -> tuple[str, int] | None:
    """Pair `text` with its assertion, or nothing when no assertion states it."""
    return None if assertion_id is None else (text, assertion_id)
