"""Learning plans for gap requirements and progress tracking (FR-33, FR-34).

A plan is advice and writes no knowledge. Completing its last step raises a pending `set_state`
proposal for review; nothing here confirms a skill by itself.
"""

from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cvforge.api.chat import Factory, ProposalView, failure_message, proposal_view
from cvforge.api.errors import engine
from cvforge.jobs.store import get_posting
from cvforge.kb import apply, queries
from cvforge.kb.vocab import EntityKind, KnowledgeState, MatchVerdict, StepKind
from cvforge.learning.progress import ProgressError, propose_completion, require_learning
from cvforge.learning.store import (
    PlanExistsError,
    StoredPlan,
    complete_step,
    create_plan,
    get_plan,
    list_plans,
)
from cvforge.llm.agents.plan import build_plan_agent, plan_prompt
from cvforge.match.store import list_matches

router = APIRouter(tags=["learning"])
Engine = Annotated[sa.Engine, Depends(engine)]


class StepView(BaseModel):
    """One step of a plan.

    Attributes:
        id: The step id.
        position: Its place in the plan.
        title: What to do.
        kind: `study`, `reading`, `exercise` or `project`.
        resource: A suggested resource, if any.
        done_when: The sign it is finished.
        completed_at: When it was completed, if it was.
    """

    id: int
    position: int
    title: str
    kind: StepKind
    resource: str | None
    done_when: str
    completed_at: datetime | None


class PlanView(BaseModel):
    """A learning plan.

    Attributes:
        id: The plan id.
        job_posting_id: The posting.
        requirement_id: The `gap` requirement it addresses (see `GET /api/jobs/{id}/gaps`).
        entity_id: The recorded entity it would confirm, if any.
        summary: The route in one sentence.
        completion_proposal_id: The pending `set_state` proposal, once every step is done.
        steps: The steps in order.
    """

    id: int
    job_posting_id: int
    requirement_id: int
    entity_id: int | None
    summary: str
    completion_proposal_id: int | None
    steps: list[StepView]


class ProgressView(BaseModel):
    """The result of completing a step.

    Attributes:
        plan: The plan after the step was marked.
        proposal: The pending `set_state` proposal if that finished the plan; empty otherwise.
    """

    plan: PlanView
    proposal: ProposalView


def _view(plan: StoredPlan) -> PlanView:
    return PlanView(
        id=plan.id,
        job_posting_id=plan.job_posting_id,
        requirement_id=plan.requirement_id,
        entity_id=plan.entity_id,
        summary=plan.summary,
        completion_proposal_id=plan.completion_proposal_id,
        steps=[
            StepView(
                id=s.id,
                position=s.position,
                title=s.title,
                kind=s.kind,
                resource=s.resource,
                done_when=s.done_when,
                completed_at=s.completed_at,
            )
            for s in plan.steps
        ],
    )


def _require(db: sa.Engine, plan_id: int) -> StoredPlan:
    plan = get_plan(db, plan_id)
    if plan is None:
        raise apply.NotFoundError(f"no learning plan {plan_id}")
    return plan


def _gap_text(db: sa.Engine, posting_id: int, requirement_id: int) -> str:
    posting = get_posting(db, posting_id)
    if posting is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    texts = {r.id: r.text for r in posting.requirements}
    match = next(
        (m for m in list_matches(db, posting_id) if m.requirement_id == requirement_id), None
    )
    if requirement_id not in texts or match is None or match.verdict is not MatchVerdict.GAP:
        raise HTTPException(409, f"requirement {requirement_id} is not a gap; no plan is made")
    return texts[requirement_id]


def _recorded_entity(db: sa.Engine, text: str) -> int | None:
    """The non-archived entity named like the requirement, if one is recorded."""
    with db.connect() as conn:
        for kind in EntityKind:
            for entity_id in queries.find_by_name(conn, kind, text):
                record = queries.get_entity(conn, entity_id)
                if record is not None and record.state is not KnowledgeState.ARCHIVED:
                    return entity_id
    return None


@router.post("/jobs/{posting_id}/gaps/{requirement_id}/plan", status_code=201)
def make_plan(posting_id: int, requirement_id: int, db: Engine, model_factory: Factory) -> PlanView:
    """Draft a learning plan for one `gap` requirement and store it.

    Args:
        posting_id: A posting id.
        requirement_id: A requirement whose stored verdict is `gap`.
        db: The knowledge-base engine.
        model_factory: Builds the model for this request.

    Returns:
        The stored plan.

    Raises:
        HTTPException: 409 if the requirement is not a gap or already has a plan; 502 if the
            model fails.
    """
    text = _gap_text(db, posting_id, requirement_id)
    with db.connect() as conn:
        skills = [
            e.name
            for e in queries.list_entities(conn, kind=EntityKind.SKILL)
            if e.state is KnowledgeState.CONFIRMED
        ]
    try:
        draft = build_plan_agent(model_factory(db)).run_sync(plan_prompt(text, skills)).output
    except Exception as exc:
        raise HTTPException(502, failure_message(exc)) from exc
    try:
        plan_id = create_plan(
            db,
            posting_id=posting_id,
            requirement_id=requirement_id,
            entity_id=_recorded_entity(db, text),
            summary=draft.summary,
            steps=[(s.title, s.kind, s.resource, s.done_when) for s in draft.steps],
        )
    except PlanExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _view(_require(db, plan_id))


@router.get("/jobs/{posting_id}/plans")
def read_plans(posting_id: int, db: Engine) -> list[PlanView]:
    """List a posting's learning plans.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The plans.
    """
    return [_view(p) for p in list_plans(db, posting_id)]


@router.get("/plans/{plan_id}")
def read_plan(plan_id: int, db: Engine) -> PlanView:
    """Read one plan.

    Args:
        plan_id: A plan id.
        db: The knowledge-base engine.

    Returns:
        The plan.

    Raises:
        NotFoundError: If there is no such plan (404).
    """
    return _view(_require(db, plan_id))


@router.post("/plans/{plan_id}/steps/{step_id}/complete")
def complete(plan_id: int, step_id: int, db: Engine) -> ProgressView:
    """Mark a step complete; finishing the last one raises a pending `set_state` proposal.

    The entity is never changed here: the proposal is accepted or rejected in review.

    Args:
        plan_id: A plan id.
        step_id: A step of that plan.
        db: The knowledge-base engine.

    Returns:
        The plan and, if it is now complete, the pending proposal.

    Raises:
        NotFoundError: If the plan or step does not exist (404).
        HTTPException: 409 if the plan's entity is not recorded as `learning`.
    """
    plan = _require(db, plan_id)
    try:
        require_learning(db, plan)
        complete_step(db, plan_id, step_id)
        proposal_id = propose_completion(db, _require(db, plan_id))
    except ProgressError as exc:
        raise HTTPException(409, str(exc)) from exc
    return ProgressView(plan=_view(_require(db, plan_id)), proposal=proposal_view(db, proposal_id))
