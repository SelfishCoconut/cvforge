"""Suggest a value for each form field from the selected CV (FR-36).

Pure: it reads a stored CV's claims and nothing else. A suggestion is derived from claims the
CV already carries, so it is as grounded as the CV is; a field no claim answers gets no
suggestion and is flagged for manual entry. Nothing here is invented, and a password field is
never suggested (ADR-0030).
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

from cvforge.cv.store import StoredClaim, StoredCv
from cvforge.forms.analyze import FormField
from cvforge.kb.vocab import ClaimSlot

_YEARS_LABEL: Final = re.compile(r"years?\b.*\bexperience|experience\b.*\byears?", re.I)
_SKILLS_LABEL: Final = re.compile(r"\bskills?\b", re.I)
_PERIOD: Final = re.compile(r"^(?:from )?(\d{4})-(\d{2})(?: to (\d{4})-(\d{2}))?$")
_TEXT_TYPES: Final = frozenset({"text", "number", "textarea"})


@dataclass(frozen=True)
class Suggestion:
    """The suggested value for one field.

    Attributes:
        key: The `FormField.key` it answers.
        value: The suggested value, or None when no stored fact answers the field.
        claim_ids: The CV claims the value was derived from; empty when `value` is None.
        reason: Why there is, or is not, a suggestion (shown beside the field).
    """

    key: str
    value: str | None
    claim_ids: tuple[int, ...]
    reason: str


def _months(claim: StoredClaim, today: date) -> tuple[int, int] | None:
    """The [start, end) span of a period claim as month numbers, or None if unreadable."""
    match = _PERIOD.match(claim.text)
    if match is None:
        return None
    start = int(match[1]) * 12 + int(match[2]) - 1
    end = int(match[3]) * 12 + int(match[4]) - 1 if match[3] else today.year * 12 + today.month - 1
    return (start, end) if end > start else None


def _experience_years(cv: StoredCv, today: date) -> tuple[int, tuple[int, ...]] | None:
    """Whole years covered by the CV's role periods (overlaps counted once), and the claims."""
    claims = [c for c in cv.claims if c.section == "Experience" and c.slot is ClaimSlot.PERIOD]
    spans = sorted(s for c in claims if (s := _months(c, today)) is not None)
    if not spans:
        return None
    total, (_, reach) = 0, (0, spans[0][0])
    for start, end in spans:
        total += max(0, end - max(start, reach))
        reach = max(reach, end)
    return total // 12, tuple(c.id for c in claims)


def _skills(cv: StoredCv) -> list[StoredClaim]:
    return [c for c in cv.claims if c.section == "Skills" and c.slot is ClaimSlot.BULLET]


def _option_for(field: FormField, value: str) -> str | None:
    """The field's own option matching `value`, or None; a choice is never made up."""
    return next((o for o in field.options if o.strip().lower() == value.lower()), None)


def _none(field: FormField, reason: str) -> Suggestion:
    return Suggestion(field.key, None, (), reason)


def _for_field(field: FormField, cv: StoredCv, today: date) -> Suggestion:
    if field.sensitive:
        return _none(field, "Secrets are never suggested; enter it yourself.")
    if _YEARS_LABEL.search(field.label):
        years = _experience_years(cv, today)
        if years is None:
            return _none(field, "The selected CV has no dated role to count years from.")
        value = str(years[0])
        if field.type in ("select", "radio"):
            chosen = _option_for(field, value)
            if chosen is None:
                return _none(field, f"The CV gives {value} years but no option says so.")
            return Suggestion(field.key, chosen, years[1], f"{value} years of roles on the CV.")
        if field.type in _TEXT_TYPES:
            return Suggestion(field.key, value, years[1], f"{value} years of roles on the CV.")
    if _SKILLS_LABEL.search(field.label) and field.type in ("text", "textarea"):
        skills = _skills(cv)
        if skills:
            return Suggestion(
                field.key,
                ", ".join(c.text for c in skills),
                tuple(c.id for c in skills),
                "The skills listed on the selected CV.",
            )
        return _none(field, "The selected CV lists no skills.")
    return _none(field, "No stored fact answers this; fill it in manually.")


def suggest_values(fields: list[FormField], cv: StoredCv, today: date) -> list[Suggestion]:
    """Suggest a value, or none, for every field of a form.

    Args:
        fields: The analysed fields.
        cv: The selected CV; its claims are the only source of values.
        today: The date an open-ended role runs to (a parameter so tests are deterministic).

    Returns:
        One suggestion per field, in field order.
    """
    return [_for_field(f, cv, today) for f in fields]
