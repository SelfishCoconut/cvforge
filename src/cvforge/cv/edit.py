"""Apply conversational edits to a CV without losing its support (FR-31).

An edit never mutates a stored CV: it turns the parent's claims into a new list, which becomes
a new version (FR-27). Each operation is checked on its own and refused, with a reason, if it
cannot be supported; the rest still apply.

- reword: replaces a bullet's text and keeps its entity and assertion; the new text must pass the
  same binding check as any claim (`basis = reword`, which includes the grounding check).
- drop: removes a bullet. Headers and periods are structure and are not dropped one by one.
- emphasize: moves what the CV already says about a stored entity to the front, or adds a skill
  the knowledge base confirms. A name nothing is stored about is refused and redirected, never
  turned into a bullet.
"""

from dataclasses import dataclass, replace
from typing import Final

import sqlalchemy as sa

from cvforge.cv.binding import claim_problem
from cvforge.cv.facts import claim_source
from cvforge.cv.model import ClaimDraft
from cvforge.cv.store import StoredClaim, StoredCv
from cvforge.kb import queries
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, EntityKind, KnowledgeState

SKILLS: Final = "Skills"
_REWORDABLE = frozenset({ClaimBasis.NAME, ClaimBasis.SUMMARY, ClaimBasis.REWORD})


@dataclass(frozen=True)
class Reword:
    """Rewrite one bullet.

    Attributes:
        claim_id: The bullet to rewrite.
        text: Its new wording.
    """

    claim_id: int
    text: str


@dataclass(frozen=True)
class Drop:
    """Remove one bullet.

    Attributes:
        claim_id: The bullet to remove.
    """

    claim_id: int


@dataclass(frozen=True)
class Emphasize:
    """Bring something the user named to the front.

    Attributes:
        name: What to emphasise, as the user said it.
    """

    name: str


Edit = Reword | Drop | Emphasize


@dataclass(frozen=True)
class EditResult:
    """What an edit produced.

    Attributes:
        claims: The new claim list, in render order.
        applied: What was done, in words.
        refused: What was not done and why.
    """

    claims: list[ClaimDraft]
    applied: list[str]
    refused: list[str]


def _draft(c: StoredClaim) -> ClaimDraft:
    return ClaimDraft(
        c.section,
        c.item_index,
        c.slot,
        c.position,
        c.basis,
        c.text,
        c.entity_id,
        c.assertion_id,
        c.link_assertion_id,
    )


def _normalize(claims: list[ClaimDraft]) -> list[ClaimDraft]:
    """Renumber items and positions so the list is dense, keeping its order."""
    item_of: dict[tuple[str, int], int] = {}
    counts: dict[tuple[str, int, ClaimSlot], int] = {}
    out: list[ClaimDraft] = []
    for c in claims:
        key = (c.section, c.item_index)
        if key not in item_of:
            item_of[key] = sum(1 for k in item_of if k[0] == c.section)
        index = item_of[key]
        slot_key = (c.section, index, c.slot)
        position = counts.get(slot_key, 0)
        counts[slot_key] = position + 1
        out.append(replace(c, item_index=index, position=position))
    return out


def _header_of(claims: list[ClaimDraft], target: ClaimDraft) -> int | None:
    return next(
        (
            c.entity_id
            for c in claims
            if c.slot is ClaimSlot.HEADER
            and (c.section, c.item_index) == (target.section, target.item_index)
        ),
        None,
    )


def _reword(
    conn: sa.Connection, claims: list[ClaimDraft], by_id: dict[int, ClaimDraft], op: Reword
) -> str | None:
    """Apply a reword in place; return the reason it was refused, or None on success."""
    old = by_id.get(op.claim_id)
    if old is None or old.slot is not ClaimSlot.BULLET or old.basis not in _REWORDABLE:
        return f"claim {op.claim_id} is not a bullet that can be reworded"
    new = replace(old, text=" ".join(op.text.split()), basis=ClaimBasis.REWORD)
    if not new.text:
        return f"claim {op.claim_id}: the new wording is empty"
    problem = claim_problem(
        conn,
        text=new.text,
        entity_id=new.entity_id,
        assertion_id=new.assertion_id,
        basis=new.basis,
        link_assertion_id=new.link_assertion_id,
        header_entity_id=_header_of(claims, old),
    )
    if problem is not None:
        return f"claim {op.claim_id} not reworded: {problem[1]}"
    claims[claims.index(old)] = new
    by_id[op.claim_id] = new
    return None


def _resolve(conn: sa.Connection, name: str) -> queries.EntityRecord | None:
    for kind in EntityKind:
        for entity_id in queries.find_by_name(conn, kind, name):
            record = queries.get_entity(conn, entity_id)
            if record is not None and record.state is KnowledgeState.CONFIRMED:
                return record
    return None


def _move_item_to_front(claims: list[ClaimDraft], head: ClaimDraft) -> None:
    """Bring the whole item `head` heads to the front of its section."""
    group = [c for c in claims if (c.section, c.item_index) == (head.section, head.item_index)]
    rest = [c for c in claims if c not in group]
    first = next((i for i, c in enumerate(rest) if c.section == head.section), len(rest))
    claims[:] = [*rest[:first], *group, *rest[first:]]


def _move_bullet_to_front(claims: list[ClaimDraft], bullet: ClaimDraft) -> None:
    """Bring a bullet to the top of its item."""
    others = [c for c in claims if c is not bullet]
    index = next(
        i
        for i, c in enumerate(others)
        if (c.section, c.item_index) == (bullet.section, bullet.item_index)
    )
    claims[:] = [*others[:index], bullet, *others[index:]]


def _move_to_front(claims: list[ClaimDraft], entity_id: int) -> bool:
    """Bring an entity's item (if it heads one) or bullet (if it is under one) to the front."""
    own = [c for c in claims if c.entity_id == entity_id]
    if not own:
        return False
    head = next((c for c in own if c.slot is ClaimSlot.HEADER), None)
    if head is not None:
        _move_item_to_front(claims, head)
    else:
        _move_bullet_to_front(claims, own[0])
    return True


def _emphasize(conn: sa.Connection, claims: list[ClaimDraft], op: Emphasize) -> str | None:
    record = _resolve(conn, op.name)
    redirect = (
        f"nothing confirmed is stored about {op.name!r}; tell me about it first (chat or a "
        "discovery question) so it can be reviewed and recorded"
    )
    if record is None:
        return redirect
    if _move_to_front(claims, record.id):
        return None
    source = claim_source(conn, record.id, ClaimBasis.NAME)
    if record.kind is not EntityKind.SKILL or source is None:
        return redirect
    text, assertion_id = source
    claims.insert(
        0,
        ClaimDraft(SKILLS, 0, ClaimSlot.BULLET, 0, ClaimBasis.NAME, text, record.id, assertion_id),
    )
    return None


def _apply_one(
    conn: sa.Connection, claims: list[ClaimDraft], by_id: dict[int, ClaimDraft], edit: Edit
) -> tuple[str | None, str]:
    """Apply one edit; return (reason it was refused or None, description if applied)."""
    if isinstance(edit, Reword):
        return _reword(conn, claims, by_id, edit), f"reworded claim {edit.claim_id}"
    if isinstance(edit, Drop):
        target = by_id.get(edit.claim_id)
        if target is None or target.slot is not ClaimSlot.BULLET:
            return f"claim {edit.claim_id} is not a bullet that can be dropped", ""
        claims.remove(target)
        return None, f"dropped claim {edit.claim_id}"
    return _emphasize(conn, claims, edit), f"emphasised {edit.name!r}"


def apply_edits(engine: sa.Engine, cv: StoredCv, edits: list[Edit]) -> EditResult:
    """Turn `cv`'s claims into the claims of an edited version.

    Args:
        engine: The knowledge-base engine.
        cv: The CV being edited; it is not changed.
        edits: The operations, in order.

    Returns:
        The new claims plus what was applied and what was refused (with reasons).
    """
    claims = [_draft(c) for c in cv.claims]
    by_id = {c.id: d for c, d in zip(cv.claims, claims, strict=True)}
    applied: list[str] = []
    refused: list[str] = []
    with engine.connect() as conn:
        for edit in edits:
            reason, done = _apply_one(conn, claims, by_id, edit)
            (refused if reason else applied).append(reason or done)
    return EditResult(_normalize(claims), applied, refused)
