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

from cvforge.cv.binding import claim_problem
from cvforge.cv.model import ClaimDraft
from cvforge.kb import apply, schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, CvStatus, GenerationMode


class WrongPostingError(Exception):
    """A CV was derived from a CV that targets a different posting."""


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
    link_assertion_id: int | None


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
        tex_path: Where its LaTeX source was written, once rendered.
        pdf_path: Where its PDF was written, once compiled.
        txt_path: Where its plain text was written, once rendered.
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
    tex_path: str | None
    pdf_path: str | None
    txt_path: str | None
    claims: tuple[StoredClaim, ...]


def _check_supported(conn: sa.Connection, claims: Sequence[ClaimDraft]) -> None:
    """Refuse the CV if any claim is not exactly what its assertion states."""
    headers = {(c.section, c.item_index): c.entity_id for c in claims if c.slot is ClaimSlot.HEADER}
    for claim in claims:
        problem = claim_problem(
            conn,
            text=claim.text,
            entity_id=claim.entity_id,
            assertion_id=claim.assertion_id,
            basis=claim.basis,
            link_assertion_id=claim.link_assertion_id,
            header_entity_id=headers.get((claim.section, claim.item_index)),
        )
        if problem is not None:
            raise UnsupportedClaimError(f"{problem[0]}: {problem[1]}")
        if not claim.section.strip():
            raise UnsupportedClaimError(f"{claim.text!r} has no section")


def _check_parent(conn: sa.Connection, parent_cv_id: int, posting_id: int) -> None:
    parent = conn.execute(
        sa.select(schema.cv.c.job_posting_id).where(schema.cv.c.id == parent_cv_id)
    ).first()
    if parent is None:
        raise apply.NotFoundError(f"no CV {parent_cv_id}")
    if parent.job_posting_id != posting_id:
        raise WrongPostingError(f"CV {parent_cv_id} belongs to another posting")


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
        WrongPostingError: If the parent CV targets a different posting.
    """
    with write_transaction(engine) as conn:
        _check_supported(conn, claims)
        if parent_cv_id is not None:
            _check_parent(conn, parent_cv_id, posting_id)
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
                        "link_assertion_id": c.link_assertion_id,
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
            r.link_assertion_id,
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
        row.tex_path,
        row.pdf_path,
        row.txt_path,
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
    """Change a CV's status, with no checks of its own.

    Only `cv.validate.finalize_cv` may use this to mark a CV final; it validates first.

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


def set_artifacts(engine: sa.Engine, cv_id: int, *, tex: str, pdf: str | None, txt: str) -> None:
    """Record where a CV's rendered files were written.

    Args:
        engine: The knowledge-base engine.
        cv_id: The `cv` id.
        tex: Path of the LaTeX source.
        pdf: Path of the compiled PDF, if it compiled.
        txt: Path of the plain-text rendering.

    Raises:
        NotFoundError: If there is no such CV.
    """
    with write_transaction(engine) as conn:
        result = conn.execute(
            sa.update(schema.cv)
            .where(schema.cv.c.id == cv_id)
            .values(tex_path=tex, pdf_path=pdf, txt_path=txt)
        )
        if result.rowcount == 0:
            raise apply.NotFoundError(f"no CV {cv_id}")
