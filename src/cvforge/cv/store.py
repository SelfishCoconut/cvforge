"""Persist generated CVs and read them back (FR-24, FR-25, FR-27).

Registered writer (ADR-0011, ADR-0024): may write `cv` and `cv_claim`, nothing else. A CV
is its claim rows. `cv_claim.entity_id` and `assertion_id` are NOT NULL foreign keys, and
`save_cv` refuses a claim that does not name an existing assertion about its entity, so a
line with no support cannot be stored (invariant 5, FR-25).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from cvforge.cv.model import ClaimDraft
from cvforge.kb import apply, queries, schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, CvStatus, GenerationMode, TargetKind


class UnsupportedClaimError(Exception):
    """A claim names no assertion, or one that is not about its entity."""


@dataclass(frozen=True)
class StoredClaim:
    """One stored line of a CV.

    Attributes:
        id: The `cv_claim` row id.
        section: The section.
        item_index: Which item of the section.
        slot: Header, subheader, period or bullet.
        position: Order among claims of the same slot in the item.
        basis: Which stored fact the text was copied from.
        text: The rendered string.
        entity_id: The entity it is about.
        assertion_id: The assertion that states it.
    """

    id: int
    section: str
    item_index: int
    slot: ClaimSlot
    position: int
    basis: ClaimBasis
    text: str
    entity_id: int
    assertion_id: int


@dataclass(frozen=True)
class StoredCv:
    """A stored CV with its claims in render order.

    Attributes:
        id: The `cv` row id.
        job_posting_id: The posting it targets.
        version: 1 for a posting's first CV, then increasing.
        parent_cv_id: The CV it was derived from, if any.
        label: A free label, if any.
        generation_mode: `automatic` or `collaborative`.
        status: `draft` or `final`.
        created_at: When it was generated.
        claims: Its claims.
    """

    id: int
    job_posting_id: int
    version: int
    parent_cv_id: int | None
    label: str | None
    generation_mode: GenerationMode
    status: CvStatus
    created_at: datetime
    claims: tuple[StoredClaim, ...]


def _check_supported(conn: sa.Connection, claim: ClaimDraft) -> None:
    assertion = queries.get_assertion(conn, claim.assertion_id)
    if (
        assertion is None
        or assertion.target_kind != TargetKind.ENTITY.value
        or assertion.target_id != claim.entity_id
    ):
        raise UnsupportedClaimError(
            f"claim {claim.text!r} names no supporting fact about subject {claim.entity_id}"
        )


def save_cv(
    engine: sa.Engine,
    posting_id: int,
    claims: Sequence[ClaimDraft],
    *,
    parent_cv_id: int | None = None,
    mode: GenerationMode = GenerationMode.AUTOMATIC,
    label: str | None = None,
) -> int:
    """Store a CV as a new version for a posting.

    Args:
        engine: The knowledge-base engine.
        posting_id: The `job_posting` id.
        claims: The claims, from `generate_cv`.
        parent_cv_id: The CV this one derives from, if any.
        mode: How it was produced.
        label: An optional label.

    Returns:
        The new `cv` id. It is a draft.

    Raises:
        UnsupportedClaimError: If any claim lacks a supporting assertion; nothing is stored.
        NotFoundError: If the parent CV does not exist.
    """
    with write_transaction(engine) as conn:
        for claim in claims:
            _check_supported(conn, claim)
        if (
            parent_cv_id is not None
            and conn.execute(
                sa.select(schema.cv.c.id).where(schema.cv.c.id == parent_cv_id)
            ).first()
            is None
        ):
            raise apply.NotFoundError(f"no CV {parent_cv_id}")
        latest = conn.execute(
            sa.select(sa.func.max(schema.cv.c.version)).where(
                schema.cv.c.job_posting_id == posting_id
            )
        ).scalar()
        cv_id = int(
            conn.execute(
                sa.insert(schema.cv)
                .values(
                    job_posting_id=posting_id,
                    version=(latest or 0) + 1,
                    parent_cv_id=parent_cv_id,
                    label=label,
                    generation_mode=mode.value,
                    status=CvStatus.DRAFT.value,
                    created_at=utc_now(),
                )
                .returning(schema.cv.c.id)
            ).scalar_one()
        )
        if claims:
            conn.execute(
                sa.insert(schema.cv_claim),
                [
                    {
                        "cv_id": cv_id,
                        "section": c.section,
                        "item_index": c.item_index,
                        "slot": c.slot.value,
                        "position": c.position,
                        "basis": c.basis.value,
                        "text": c.text,
                        "entity_id": c.entity_id,
                        "assertion_id": c.assertion_id,
                    }
                    for c in claims
                ],
            )
    return cv_id


def _claims(conn: sa.Connection, cv_id: int) -> tuple[StoredClaim, ...]:
    rows = conn.execute(
        sa.select(schema.cv_claim)
        .where(schema.cv_claim.c.cv_id == cv_id)
        .order_by(schema.cv_claim.c.id)
    )
    return tuple(
        StoredClaim(
            r.id,
            r.section,
            r.item_index,
            ClaimSlot(r.slot),
            r.position,
            ClaimBasis(r.basis),
            r.text,
            r.entity_id,
            r.assertion_id,
        )
        for r in rows
    )


def _stored(conn: sa.Connection, row: sa.Row[Any]) -> StoredCv:
    return StoredCv(
        row.id,
        row.job_posting_id,
        row.version,
        row.parent_cv_id,
        row.label,
        GenerationMode(row.generation_mode),
        CvStatus(row.status),
        row.created_at,
        _claims(conn, row.id),
    )


def get_cv(engine: sa.Engine, cv_id: int) -> StoredCv | None:
    """Read one CV with its claims.

    Args:
        engine: The knowledge-base engine.
        cv_id: The `cv` id.

    Returns:
        The CV, or None if there is none with that id.
    """
    with engine.connect() as conn:
        row = conn.execute(sa.select(schema.cv).where(schema.cv.c.id == cv_id)).first()
        return None if row is None else _stored(conn, row)


def list_cvs(engine: sa.Engine, posting_id: int) -> list[StoredCv]:
    """List a posting's CVs, oldest version first.

    Args:
        engine: The knowledge-base engine.
        posting_id: The `job_posting` id.

    Returns:
        The CVs ordered by version.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(schema.cv)
            .where(schema.cv.c.job_posting_id == posting_id)
            .order_by(schema.cv.c.version)
        ).all()
        return [_stored(conn, row) for row in rows]


def set_status(engine: sa.Engine, cv_id: int, status: CvStatus) -> None:
    """Change a CV's status. Callers must have validated it before marking it final.

    Args:
        engine: The knowledge-base engine.
        cv_id: The `cv` id.
        status: The new status.

    Raises:
        NotFoundError: If there is no such CV.
    """
    with write_transaction(engine) as conn:
        result = conn.execute(
            sa.update(schema.cv).where(schema.cv.c.id == cv_id).values(status=status.value)
        )
        if result.rowcount == 0:
            raise apply.NotFoundError(f"no CV {cv_id}")
