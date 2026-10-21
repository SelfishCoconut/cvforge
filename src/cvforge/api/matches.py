"""Match a stored posting's requirements against the knowledge base (FR-21).

Matching reads the knowledge base and writes only `match` rows; it never creates
knowledge. The verdicts are decided by the database; the optional model judge can only
choose among entities the engine itself offered (ADR-0023).
"""

import logging
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cvforge.api.chat import Embedder, Factory
from cvforge.api.errors import engine
from cvforge.jobs.store import StoredPosting, get_posting
from cvforge.kb import apply
from cvforge.kb.vocab import MatchVerdict, RequirementKind
from cvforge.llm.agents.adjacency import ModelJudge
from cvforge.match.evidence import DetailedMatch, detailed_matches, gap_report
from cvforge.match.store import list_matches, replace_matches
from cvforge.match.verdicts import match_posting

logger = logging.getLogger(__name__)

router = APIRouter(tags=["match"])
Engine = Annotated[sa.Engine, Depends(engine)]


class EvidenceView(BaseModel):
    """A span of source text.

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


class SupportView(BaseModel):
    """An entity a verdict rests on.

    Attributes:
        entity_id: The entity (fetch it with `GET /api/entities/{id}`).
        name: Its name.
        kind: Its kind.
        state: Its current knowledge state.
        archived: True if it was archived after the match, so it no longer backs a claim.
        evidence: Spans stating the entity or one of its recorded uses.
    """

    entity_id: int
    name: str
    kind: str
    state: str
    archived: bool
    evidence: list[EvidenceView]


class MatchView(BaseModel):
    """The verdict for one requirement.

    Attributes:
        requirement_id: The requirement judged.
        kind: The requirement's kind.
        text: What the posting asks.
        verdict: `satisfied`, `evidenced`, `undocumented` or `gap`.
        score: Closeness of the best backing or plausible entity, if any.
        rationale: Why.
        support: Backing entities with evidence; empty for `undocumented` and `gap`.
    """

    requirement_id: int
    kind: RequirementKind
    text: str
    verdict: MatchVerdict
    score: float | None
    rationale: str
    support: list[SupportView]


def _support(detail: DetailedMatch) -> list[SupportView]:
    return [
        SupportView(
            entity_id=e.entity_id,
            name=e.name,
            kind=e.kind.value,
            state=e.state.value,
            archived=e.archived,
            evidence=[EvidenceView(**vars(span)) for span in e.evidence],
        )
        for e in detail.support
    ]


def _views(db: sa.Engine, posting_id: int) -> list[MatchView]:
    posting = _posting(db, posting_id)
    by_id = {r.id: r for r in posting.requirements}
    return [
        MatchView(
            requirement_id=d.match.requirement_id,
            kind=by_id[d.match.requirement_id].kind,
            text=by_id[d.match.requirement_id].text,
            verdict=d.match.verdict,
            score=d.match.score,
            rationale=d.match.rationale,
            support=_support(d),
        )
        for d in detailed_matches(db, list_matches(db, posting_id))
        if d.match.requirement_id in by_id
    ]


def _posting(db: sa.Engine, posting_id: int) -> StoredPosting:
    posting = get_posting(db, posting_id)
    if posting is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    return posting


def _judge(db: sa.Engine, embedder: Embedder, model_factory: Factory) -> ModelJudge | None:
    """The adjacency judge, or None when there is no embedder or no model can be built."""
    if embedder is None:
        return None
    try:
        return ModelJudge(model_factory(db))
    except Exception:
        return None


@router.post("/jobs/{posting_id}/match")
def run_match(
    posting_id: int, db: Engine, embedder: Embedder, model_factory: Factory
) -> list[MatchView]:
    """Match every requirement of a posting and store the verdicts, replacing any earlier run.

    Args:
        posting_id: A posting id from `POST /api/jobs`.
        db: The knowledge-base engine.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for the optional adjacency judge.

    Returns:
        One verdict per requirement.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    judge = _judge(db, embedder, model_factory)
    results = match_posting(db, posting_id, embedder=embedder, judge=judge)
    if results is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    replace_matches(db, posting_id, results)
    return _views(db, posting_id)


@router.get("/jobs/{posting_id}/match")
def read_match(posting_id: int, db: Engine) -> list[MatchView]:
    """Read the stored verdicts for a posting; empty until a match has been run.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The verdicts in requirement order.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    return _views(db, posting_id)


class GapView(BaseModel):
    """A requirement the knowledge base does not back.

    Attributes:
        requirement_id: The requirement, linking back to the posting.
        kind: The requirement's kind.
        text: What the posting asks.
        verdict: `undocumented` (plausible, unrecorded) or `gap`.
        score: Closeness of the nearest plausible entity, if any.
        rationale: Why.
    """

    requirement_id: int
    kind: RequirementKind
    text: str
    verdict: MatchVerdict
    score: float | None
    rationale: str


@router.get("/jobs/{posting_id}/gaps")
def read_gaps(posting_id: int, db: Engine) -> list[GapView]:
    """List a posting's `undocumented` and `gap` requirements from its stored matches.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The gap report; empty when everything is backed or no match has been run.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    posting = _posting(db, posting_id)
    by_id = {r.id: r for r in posting.requirements}
    return [
        GapView(
            requirement_id=g.requirement_id,
            kind=by_id[g.requirement_id].kind,
            text=by_id[g.requirement_id].text,
            verdict=g.verdict,
            score=g.score,
            rationale=g.rationale,
        )
        for g in gap_report(db, posting)
        if g.requirement_id in by_id
    ]
