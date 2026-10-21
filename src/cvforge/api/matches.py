"""Match a stored posting's requirements against the knowledge base (FR-21).

Matching reads the knowledge base and writes only `match` rows; it never creates
knowledge. The verdicts are decided by the database; the optional model judge can only
choose among entities the engine itself offered (ADR-0023).
"""

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cvforge.api.chat import Embedder, Factory
from cvforge.api.errors import engine
from cvforge.jobs.store import get_posting
from cvforge.kb import apply
from cvforge.kb.vocab import MatchVerdict, RequirementKind
from cvforge.llm.agents.adjacency import ModelJudge
from cvforge.match.store import StoredMatch, list_matches, replace_matches
from cvforge.match.verdicts import match_posting

router = APIRouter(tags=["match"])
Engine = Annotated[sa.Engine, Depends(engine)]


class MatchView(BaseModel):
    """The verdict for one requirement.

    Attributes:
        requirement_id: The requirement judged.
        kind: The requirement's kind.
        text: What the posting asks.
        verdict: `satisfied`, `evidenced`, `undocumented` or `gap`.
        score: Closeness of the best backing or plausible entity, if any.
        rationale: Why.
        support: Backing entity ids; empty for `undocumented` and `gap`.
    """

    requirement_id: int
    kind: RequirementKind
    text: str
    verdict: MatchVerdict
    score: float | None
    rationale: str
    support: list[int]


def _views(db: sa.Engine, posting_id: int, matches: list[StoredMatch]) -> list[MatchView]:
    posting = get_posting(db, posting_id)
    if posting is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    by_id = {r.id: r for r in posting.requirements}
    return [
        MatchView(
            requirement_id=m.requirement_id,
            kind=by_id[m.requirement_id].kind,
            text=by_id[m.requirement_id].text,
            verdict=m.verdict,
            score=m.score,
            rationale=m.rationale,
            support=list(m.support),
        )
        for m in matches
        if m.requirement_id in by_id
    ]


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
    judge = ModelJudge(model_factory(db)) if embedder is not None else None
    results = match_posting(db, posting_id, embedder=embedder, judge=judge)
    if results is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    replace_matches(db, posting_id, results)
    return _views(db, posting_id, list_matches(db, posting_id))


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
    return _views(db, posting_id, list_matches(db, posting_id))
