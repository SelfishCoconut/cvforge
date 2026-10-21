"""Turn a finished learning plan into a reviewable state change (FR-34).

Completing every step of a plan never touches the entity. It records the user's own statement
as manual provenance and raises a *pending proposal* with one `set_state` operation
(`learning` to `confirmed`); the user accepts or rejects it like any other change (invariant 4).
Tracking is only possible for an entity that was recorded as `learning`: it never creates one.
"""

import sqlalchemy as sa

from cvforge.kb import apply, intake, queries
from cvforge.kb.models import SetState
from cvforge.kb.vocab import KnowledgeState, Origin, SourceKind
from cvforge.learning.store import StoredPlan, record_completion_proposal


class ProgressError(Exception):
    """A plan cannot be tracked: it has no recorded entity, or the entity is not being learned."""


def require_learning(engine: sa.Engine, plan: StoredPlan) -> int:
    """The id of the plan's entity, which must be recorded as `learning`.

    Args:
        engine: The knowledge-base engine.
        plan: The plan.

    Returns:
        The entity id.

    Raises:
        ProgressError: If the plan has no recorded entity, or it is not in state `learning`.
    """
    if plan.entity_id is None:
        raise ProgressError("nothing is recorded for this requirement; record it as learning first")
    with engine.connect() as conn:
        entity = queries.get_entity(conn, plan.entity_id)
    if entity is None or entity.state is not KnowledgeState.LEARNING:
        state = "missing" if entity is None else entity.state.value
        raise ProgressError(f"the entity is {state}, not learning; record it as learning first")
    return plan.entity_id


def propose_completion(engine: sa.Engine, plan: StoredPlan) -> int | None:
    """Raise the `set_state` proposal if, and only if, every step is complete.

    Args:
        engine: The knowledge-base engine.
        plan: The plan as it stands after the latest step was marked.

    Returns:
        The pending proposal id (the earlier one if already raised), or None while steps remain.

    Raises:
        ProgressError: If the entity is not recorded as `learning`.
    """
    if any(step.completed_at is None for step in plan.steps):
        return None
    if plan.completion_proposal_id is not None:
        return plan.completion_proposal_id
    entity_id = require_learning(engine, plan)
    source = apply.record_source(engine, SourceKind.MANUAL, f"learning plan {plan.id} completed")
    evidence = apply.record_evidence(
        engine,
        source,
        f"plan:{plan.id}",
        f"All {len(plan.steps)} steps of the learning plan were marked complete.",
    )
    stored = intake.propose(
        engine,
        origin=Origin.CHAT,
        source_id=source,
        summary=f"learning plan {plan.id} completed: confirm the skill",
        payloads=[SetState(entity=entity_id, state=KnowledgeState.CONFIRMED, evidence_id=evidence)],
    )
    if stored is None:  # pragma: no cover - one payload always yields a proposal
        raise ProgressError("the completion proposal could not be recorded")
    record_completion_proposal(engine, plan.id, stored.proposal_id)
    return stored.proposal_id
