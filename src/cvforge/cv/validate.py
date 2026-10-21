"""Check a stored CV against the knowledge base before it is presented (FR-24, FR-29, NFR-05).

Nothing is trusted from the CV's own rows. Each claim's text is recomputed from the live
knowledge base and compared; its assertion must exist and be about its entity; its entity
must still be confirmed. Across claims the validator also checks that full-time roles do not
overlap, that a skill's recorded use fits the period of what it was used in, and that the CV
mentions every required skill the candidate is `satisfied` on. A CV with any issue cannot be
marked final or rendered.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import sqlalchemy as sa

from cvforge.cv.binding import claim_problem
from cvforge.cv.store import StoredClaim, StoredCv, get_cv, set_status
from cvforge.jobs.store import get_posting
from cvforge.kb import apply, queries
from cvforge.kb.vocab import (
    ClaimSlot,
    CvStatus,
    EntityKind,
    KnowledgeState,
    MatchVerdict,
    Rel,
    RequirementKind,
)
from cvforge.match.store import list_matches

_FULL_TIME = frozenset({"full-time", "full time", "fulltime"})


@dataclass(frozen=True)
class Issue:
    """One problem found in a CV.

    Attributes:
        code: A stable machine name (`unsupported`, `text_mismatch`, `inactive_entity`, ...).
        message: What is wrong, for people.
        claim_id: The claim concerned, if the problem is about one.
    """

    code: str
    message: str
    claim_id: int | None = None


def _claim_issues(conn: sa.Connection, cv: StoredCv, claim: StoredClaim) -> list[Issue]:
    header = next(
        (
            c.entity_id
            for c in cv.claims
            if c.slot is ClaimSlot.HEADER
            and (c.section, c.item_index) == (claim.section, claim.item_index)
        ),
        None,
    )
    problem = claim_problem(
        conn,
        text=claim.text,
        entity_id=claim.entity_id,
        assertion_id=claim.assertion_id,
        basis=claim.basis,
        link_assertion_id=claim.link_assertion_id,
        header_entity_id=header,
    )
    return [] if problem is None else [Issue(problem[0], problem[1], claim.id)]


def _day(value: Any) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _overlapping_roles(conn: sa.Connection, cv: StoredCv) -> list[Issue]:
    """Full-time roles whose recorded dates overlap; an open end runs to the far future."""
    spans: list[tuple[date, date, str]] = []
    for entity_id in dict.fromkeys(c.entity_id for c in cv.claims):
        role = queries.get_entity(conn, entity_id)
        if role is None or role.kind is not EntityKind.ROLE:
            continue
        kind = str(role.attributes.get("employment_type") or "").lower()
        start = _day(role.attributes.get("started_at"))
        if kind in _FULL_TIME and start is not None:
            spans.append((start, _day(role.attributes.get("ended_at")) or date.max, role.name))
    return [
        Issue("overlapping_roles", f"full-time roles {a[2]!r} and {b[2]!r} overlap in time")
        for i, a in enumerate(spans)
        for b in spans[i + 1 :]
        if a[0] <= b[1] and b[0] <= a[1]
    ]


def _use_outside_period(conn: sa.Connection, cv: StoredCv) -> list[Issue]:
    """Skills whose recorded use falls outside the period of what they were used in."""
    issues: list[Issue] = []
    skills = {c.entity_id for c in cv.claims}
    for skill_id in sorted(skills):
        skill = queries.get_entity(conn, skill_id)
        if skill is None or skill.kind is not EntityKind.SKILL:
            continue
        for edge in queries.neighbours(conn, skill_id):
            if edge.rel != Rel.USED_IN.value:
                continue
            other = queries.get_entity(
                conn, edge.dst_id if edge.src_id == skill_id else edge.src_id
            )
            if other is None:
                continue
            first, last = _day(edge.started_at), _day(edge.ended_at)
            start, end = (
                _day(other.attributes.get("started_at")),
                _day(other.attributes.get("ended_at")),
            )
            if (first and start and first < start) or (last and end and last > end):
                issues.append(
                    Issue(
                        "inconsistent_period",
                        f"{skill.name!r} is recorded as used in {other.name!r} outside that period",
                    )
                )
    return issues


def _missing_required(engine: sa.Engine, conn: sa.Connection, cv: StoredCv) -> list[Issue]:
    """Required requirements the candidate is `satisfied` on that the CV never mentions."""
    posting = get_posting(engine, cv.job_posting_id)
    if posting is None:
        return []
    present = {c.entity_id for c in cv.claims}
    matches = {m.requirement_id: m for m in list_matches(engine, cv.job_posting_id)}
    issues: list[Issue] = []
    for requirement in posting.requirements:
        match = matches.get(requirement.id)
        if requirement.kind is not RequirementKind.REQUIRED or match is None:
            continue
        live = {
            e
            for e in match.support
            if (r := queries.get_entity(conn, e)) and r.state is KnowledgeState.CONFIRMED
        }
        if match.verdict is MatchVerdict.SATISFIED and live and not (live & present):
            issues.append(
                Issue(
                    "incomplete_coverage",
                    f"required {requirement.text!r} is satisfied by stored facts but not on the CV",
                )
            )
    return issues


def validate_cv(engine: sa.Engine, cv: StoredCv) -> list[Issue]:
    """Validate a CV against the live knowledge base.

    Args:
        engine: The knowledge-base engine.
        cv: The stored CV.

    Returns:
        Every issue found; empty means the CV may be presented.
    """
    with engine.connect() as conn:
        claim_issues = [issue for claim in cv.claims for issue in _claim_issues(conn, cv, claim)]
        return [
            *claim_issues,
            *_overlapping_roles(conn, cv),
            *_use_outside_period(conn, cv),
            *_missing_required(engine, conn, cv),
        ]


def finalize_cv(engine: sa.Engine, cv_id: int) -> list[Issue]:
    """Mark a CV final if, and only if, it validates now.

    This is the one sanctioned way to reach the `final` status: `set_status` is a bare writer
    and does not check anything.

    Args:
        engine: The knowledge-base engine.
        cv_id: The CV to finalise.

    Returns:
        The issues that stopped it; empty means the CV is now final.

    Raises:
        NotFoundError: If there is no such CV.
    """
    cv = get_cv(engine, cv_id)
    if cv is None:
        raise apply.NotFoundError(f"no CV {cv_id}")
    issues = validate_cv(engine, cv)
    if not issues:
        set_status(engine, cv_id, CvStatus.FINAL)
    return issues
