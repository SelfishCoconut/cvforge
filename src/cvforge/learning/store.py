"""Persist learning plans and track their steps (FR-33, FR-34).

Registered writer (ADR-0011, ADR-0029): may write `learning_plan` and `learning_step`, nothing
else. A plan is advice about a gap, not knowledge, so it carries no assertion. Finishing a plan
never changes an entity: `learning.progress` turns completion into a *proposal* for review.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from cvforge.kb import apply, schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import StepKind


@dataclass(frozen=True)
class StoredStep:
    """One step of a stored plan.

    Attributes:
        id: The `learning_step` id.
        position: Its place in the plan.
        title: What to do.
        kind: What sort of step it is.
        resource: A suggested resource, if any.
        done_when: The sign it is finished.
        completed_at: When it was marked complete, if it was.
    """

    id: int
    position: int
    title: str
    kind: StepKind
    resource: str | None
    done_when: str
    completed_at: datetime | None


@dataclass(frozen=True)
class StoredPlan:
    """A stored plan with its steps.

    Attributes:
        id: The `learning_plan` id.
        job_posting_id: The posting whose gap it addresses.
        requirement_id: The `gap` requirement it was generated for (FR-23 link).
        entity_id: The recorded entity it would move to `confirmed`, if one matched.
        summary: The route in one sentence.
        created_at: When it was generated.
        completion_proposal_id: The pending `set_state` proposal raised on completion, if any.
        steps: The steps in order.
    """

    id: int
    job_posting_id: int
    requirement_id: int
    entity_id: int | None
    summary: str
    created_at: datetime
    completion_proposal_id: int | None
    steps: tuple[StoredStep, ...]


class PlanExistsError(Exception):
    """A requirement already has a plan."""


def create_plan(
    engine: sa.Engine,
    *,
    posting_id: int,
    requirement_id: int,
    entity_id: int | None,
    summary: str,
    steps: Sequence[tuple[str, StepKind, str | None, str]],
) -> int:
    """Store a plan and its steps.

    Args:
        engine: The knowledge-base engine.
        posting_id: The posting.
        requirement_id: The `gap` requirement.
        entity_id: The recorded entity the plan would confirm, if any.
        summary: The route in one sentence.
        steps: (title, kind, resource, done_when) in order.

    Returns:
        The new plan id.

    Raises:
        PlanExistsError: If the requirement already has a plan.
    """
    with write_transaction(engine) as conn:
        if conn.execute(
            sa.select(schema.learning_plan.c.id).where(
                schema.learning_plan.c.requirement_id == requirement_id
            )
        ).first():
            raise PlanExistsError(f"gap {requirement_id} already has a plan")
        plan_id = int(
            conn.execute(
                sa.insert(schema.learning_plan)
                .values(
                    job_posting_id=posting_id,
                    requirement_id=requirement_id,
                    entity_id=entity_id,
                    summary=summary,
                    created_at=utc_now(),
                )
                .returning(schema.learning_plan.c.id)
            ).scalar_one()
        )
        conn.execute(
            sa.insert(schema.learning_step),
            [
                {
                    "plan_id": plan_id,
                    "position": i,
                    "title": title,
                    "kind": kind.value,
                    "resource": resource,
                    "done_when": done_when,
                }
                for i, (title, kind, resource, done_when) in enumerate(steps)
            ],
        )
    return plan_id


def _plan(conn: sa.Connection, row: sa.Row[Any]) -> StoredPlan:
    steps = conn.execute(
        sa.select(schema.learning_step)
        .where(schema.learning_step.c.plan_id == row.id)
        .order_by(schema.learning_step.c.position)
    )
    return StoredPlan(
        row.id,
        row.job_posting_id,
        row.requirement_id,
        row.entity_id,
        row.summary,
        row.created_at,
        row.completion_proposal_id,
        tuple(
            StoredStep(
                s.id, s.position, s.title, StepKind(s.kind), s.resource, s.done_when, s.completed_at
            )
            for s in steps
        ),
    )


def get_plan(engine: sa.Engine, plan_id: int) -> StoredPlan | None:
    """Read one plan with its steps.

    Args:
        engine: The knowledge-base engine.
        plan_id: The `learning_plan` id.

    Returns:
        The plan, or None if there is none.
    """
    with engine.connect() as conn:
        row = conn.execute(
            sa.select(schema.learning_plan).where(schema.learning_plan.c.id == plan_id)
        ).first()
        return None if row is None else _plan(conn, row)


def list_plans(engine: sa.Engine, posting_id: int) -> list[StoredPlan]:
    """List a posting's plans in requirement order.

    Args:
        engine: The knowledge-base engine.
        posting_id: The posting.

    Returns:
        The plans.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(schema.learning_plan)
            .where(schema.learning_plan.c.job_posting_id == posting_id)
            .order_by(schema.learning_plan.c.requirement_id)
        ).all()
        return [_plan(conn, row) for row in rows]


def complete_step(engine: sa.Engine, plan_id: int, step_id: int) -> None:
    """Mark a step complete (idempotent: a completed step keeps its first completion time).

    Args:
        engine: The knowledge-base engine.
        plan_id: The plan.
        step_id: The step, which must belong to that plan.

    Raises:
        NotFoundError: If the plan has no such step.
    """
    with write_transaction(engine) as conn:
        result = conn.execute(
            sa.update(schema.learning_step)
            .where(
                schema.learning_step.c.id == step_id,
                schema.learning_step.c.plan_id == plan_id,
                schema.learning_step.c.completed_at.is_(None),
            )
            .values(completed_at=utc_now())
        )
        exists = conn.execute(
            sa.select(schema.learning_step.c.id).where(
                schema.learning_step.c.id == step_id, schema.learning_step.c.plan_id == plan_id
            )
        ).first()
        if result.rowcount == 0 and exists is None:
            raise apply.NotFoundError(f"plan {plan_id} has no step {step_id}")


def record_completion_proposal(engine: sa.Engine, plan_id: int, proposal_id: int) -> None:
    """Remember the `set_state` proposal raised when a plan was finished.

    Args:
        engine: The knowledge-base engine.
        plan_id: The plan.
        proposal_id: The pending proposal.
    """
    with write_transaction(engine) as conn:
        conn.execute(
            sa.update(schema.learning_plan)
            .where(schema.learning_plan.c.id == plan_id)
            .values(completion_proposal_id=proposal_id)
        )
