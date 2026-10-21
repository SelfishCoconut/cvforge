"""Generate, read, validate and finalise CVs for a matched posting (FR-24, FR-25, FR-29).

A CV is generated from stored facts only (ADR-0024). Marking one final is refused unless it
validates against the live knowledge base.
"""

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from cvforge.api.errors import engine
from cvforge.cv.generate import generate_cv
from cvforge.cv.store import StoredCv, get_cv, list_cvs, save_cv, set_status
from cvforge.cv.validate import Issue, validate_cv
from cvforge.jobs.store import get_posting
from cvforge.kb import apply, queries
from cvforge.kb.vocab import ClaimSlot, CvStatus, GenerationMode, TargetKind
from cvforge.match.store import list_matches

router = APIRouter(tags=["cv"])
Engine = Annotated[sa.Engine, Depends(engine)]


class ClaimView(BaseModel):
    """One line of a CV.

    Attributes:
        id: The claim id, for `GET /api/cvs/{cv}/claims/{id}`.
        slot: Header, subheader, period or bullet.
        text: The rendered string, copied from a stored fact.
        entity_id: The entity it is about.
        assertion_id: The assertion that states it.
    """

    id: int
    slot: ClaimSlot
    text: str
    entity_id: int
    assertion_id: int


class ItemView(BaseModel):
    """One item (a role, project, degree...) of a section.

    Attributes:
        claims: Its claims in render order.
    """

    claims: list[ClaimView]


class SectionView(BaseModel):
    """A section of a CV.

    Attributes:
        title: The section title (template structure, not a claim).
        items: Its items.
    """

    title: str
    items: list[ItemView]


class CvView(BaseModel):
    """A stored CV.

    Attributes:
        id: The CV id.
        job_posting_id: The posting it targets.
        version: Its version for that posting.
        parent_cv_id: The CV it derives from, if any.
        generation_mode: `automatic` or `collaborative`.
        status: `draft` or `final`.
        sections: Its content.
    """

    id: int
    job_posting_id: int
    version: int
    parent_cv_id: int | None
    generation_mode: GenerationMode
    status: CvStatus
    sections: list[SectionView]


class GenerateRequest(BaseModel):
    """What to generate from.

    Attributes:
        parent_cv_id: The CV this one derives from, if any.
    """

    parent_cv_id: int | None = None


class IssueView(BaseModel):
    """A problem found by validation.

    Attributes:
        code: A stable machine name.
        message: What is wrong.
        claim_id: The claim concerned, if any.
    """

    code: str
    message: str
    claim_id: int | None


class ValidationView(BaseModel):
    """The result of validating a CV.

    Attributes:
        valid: True if there are no issues.
        issues: Every issue found.
    """

    valid: bool
    issues: list[IssueView]


class CvEvidenceView(BaseModel):
    """The source span a fact comes from.

    Attributes:
        source_id: The source.
        source_kind: `conversation`, `document`, `web` or `manual`.
        source_label: The source's label.
        locator: Where in the source.
        excerpt: The literal text.
    """

    source_id: int
    source_kind: str
    source_label: str
    locator: str
    excerpt: str


class ClaimDetail(BaseModel):
    """A claim resolved to the exact stored fact and its evidence.

    Attributes:
        claim: The claim.
        entity_name: The entity it is about.
        entity_state: That entity's current knowledge state.
        field: The field the assertion states (None = the entity's existence).
        evidence: The source span behind the assertion.
    """

    claim: ClaimView
    entity_name: str
    entity_state: str
    field: str | None
    evidence: CvEvidenceView


def _view(cv: StoredCv) -> CvView:
    sections: dict[str, dict[int, list[ClaimView]]] = {}
    for c in cv.claims:
        sections.setdefault(c.section, {}).setdefault(c.item_index, []).append(
            ClaimView(
                id=c.id,
                slot=c.slot,
                text=c.text,
                entity_id=c.entity_id,
                assertion_id=c.assertion_id,
            )
        )
    return CvView(
        id=cv.id,
        job_posting_id=cv.job_posting_id,
        version=cv.version,
        parent_cv_id=cv.parent_cv_id,
        generation_mode=cv.generation_mode,
        status=cv.status,
        sections=[
            SectionView(title=t, items=[ItemView(claims=items[i]) for i in sorted(items)])
            for t, items in sections.items()
        ],
    )


def _require(db: sa.Engine, cv_id: int) -> StoredCv:
    cv = get_cv(db, cv_id)
    if cv is None:
        raise apply.NotFoundError(f"no CV {cv_id}")
    return cv


def _issue_view(issue: Issue) -> IssueView:
    return IssueView(code=issue.code, message=issue.message, claim_id=issue.claim_id)


@router.post("/jobs/{posting_id}/cvs", status_code=201)
def create_cv(posting_id: int, body: GenerateRequest, db: Engine) -> CvView:
    """Generate a CV for a matched posting from stored facts only.

    Args:
        posting_id: A posting id.
        body: Optionally the CV this one derives from.
        db: The knowledge-base engine.

    Returns:
        The new draft CV.

    Raises:
        NotFoundError: If the posting or the parent CV does not exist (404).
        HTTPException: 409 if the posting has requirements but has not been matched.
    """
    posting = get_posting(db, posting_id)
    if posting is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    if posting.requirements and not list_matches(db, posting_id):
        raise HTTPException(409, "match the posting's requirements before generating a CV")
    cv_id = save_cv(db, posting_id, generate_cv(db, posting_id), parent_cv_id=body.parent_cv_id)
    return _view(_require(db, cv_id))


@router.get("/jobs/{posting_id}/cvs")
def list_posting_cvs(posting_id: int, db: Engine) -> list[CvView]:
    """List a posting's CVs, oldest version first.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The CVs.
    """
    return [_view(cv) for cv in list_cvs(db, posting_id)]


@router.get("/cvs/{cv_id}")
def read_cv(cv_id: int, db: Engine) -> CvView:
    """Read one CV.

    Args:
        cv_id: A CV id.
        db: The knowledge-base engine.

    Returns:
        The CV with its claims.

    Raises:
        NotFoundError: If there is no such CV (404).
    """
    return _view(_require(db, cv_id))


@router.get("/cvs/{cv_id}/claims/{claim_id}")
def read_claim(cv_id: int, claim_id: int, db: Engine) -> ClaimDetail:
    """Resolve a claim to the exact stored fact and the evidence behind it.

    Args:
        cv_id: A CV id.
        claim_id: A claim id in that CV.
        db: The knowledge-base engine.

    Returns:
        The claim, its entity and the source span.

    Raises:
        NotFoundError: If the CV, the claim, or its entity or assertion is missing (404).
    """
    cv = _require(db, cv_id)
    claim = next((c for c in cv.claims if c.id == claim_id), None)
    if claim is None:
        raise apply.NotFoundError(f"CV {cv_id} has no claim {claim_id}")
    with db.connect() as conn:
        entity = queries.get_entity(conn, claim.entity_id)
        spans = queries.provenance(conn, TargetKind.ENTITY, claim.entity_id)
    span = next((p for p in spans if p.assertion_id == claim.assertion_id), None)
    if entity is None or span is None:
        raise apply.NotFoundError(f"claim {claim_id} no longer resolves to a stored fact")
    return ClaimDetail(
        claim=ClaimView(
            id=claim.id,
            slot=claim.slot,
            text=claim.text,
            entity_id=claim.entity_id,
            assertion_id=claim.assertion_id,
        ),
        entity_name=entity.name,
        entity_state=entity.state.value,
        field=span.field,
        evidence=CvEvidenceView(
            source_id=span.source_id,
            source_kind=span.source_kind,
            source_label=span.source_label,
            locator=span.locator,
            excerpt=span.excerpt,
        ),
    )


@router.post("/cvs/{cv_id}/validate")
def validate(cv_id: int, db: Engine) -> ValidationView:
    """Validate a CV against the live knowledge base.

    Args:
        cv_id: A CV id.
        db: The knowledge-base engine.

    Returns:
        Whether it is valid, and every issue found.
    """
    issues = validate_cv(db, _require(db, cv_id))
    return ValidationView(valid=not issues, issues=[_issue_view(i) for i in issues])


@router.post("/cvs/{cv_id}/final")
def finalise(cv_id: int, db: Engine, response: Response) -> CvView:
    """Mark a CV final, only if it validates.

    Args:
        cv_id: A CV id.
        db: The knowledge-base engine.
        response: The response, unused on success.

    Returns:
        The CV, now final.

    Raises:
        HTTPException: 409 listing the issues if validation fails; nothing changes.
    """
    issues = validate_cv(db, _require(db, cv_id))
    if issues:
        detail = "; ".join(f"{i.code}: {i.message}" for i in issues)
        raise HTTPException(409, f"the CV does not validate and cannot be final: {detail}")
    set_status(db, cv_id, CvStatus.FINAL)
    return _view(_require(db, cv_id))
