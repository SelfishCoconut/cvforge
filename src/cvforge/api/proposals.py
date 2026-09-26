"""Review endpoints: read a proposal, decide each operation, commit (FR-09, FR-10).

There is no endpoint that creates entities, edges or assertions directly: the
only route to them is committing a reviewed proposal.
"""

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, JsonValue

from cvforge.api.errors import connection, engine
from cvforge.kb import apply, queries

router = APIRouter(tags=["review"])
Conn = Annotated[sa.Connection, Depends(connection)]
Engine = Annotated[sa.Engine, Depends(engine)]


class Review(BaseModel):
    """A reviewer's decision on one operation.

    Attributes:
        decision: ``accept``, ``edit`` or ``reject``.
        edited_payload: The replacement payload, for ``edit`` only.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "edit", "reject"]
    edited_payload: dict[str, JsonValue] | None = None


class Committed(BaseModel):
    """What a commit wrote.

    Attributes:
        commit_id: The `commit_log` row.
        applied_operation_ids: Applied operations, in order.
        entity_ids: For each applied `create_entity` seq, the entity it resolved to.
    """

    commit_id: int
    applied_operation_ids: list[int]
    entity_ids: dict[int, int]


def _proposal(conn: sa.Connection, proposal_id: int) -> queries.ProposalRecord:
    found = queries.get_proposal(conn, proposal_id)
    if found is None:
        raise HTTPException(404, f"proposal {proposal_id} does not exist")
    return found


@router.get("/proposals/{proposal_id}")
def get_proposal(conn: Conn, proposal_id: int) -> queries.ProposalRecord:
    """Return a proposal and its operations.

    Args:
        conn: Read connection.
        proposal_id: The proposal id.

    Returns:
        The proposal.
    """
    return _proposal(conn, proposal_id)


@router.post("/proposals/{proposal_id}/operations/{operation_id}/review")
def review(db: Engine, proposal_id: int, operation_id: int, body: Review) -> queries.ProposalRecord:
    """Accept, edit or reject one operation; its siblings are untouched.

    Args:
        db: The engine. The decision is written through `kb.apply`.
        proposal_id: The proposal the operation must belong to.
        operation_id: The operation.
        body: The decision.

    Returns:
        The proposal after the decision.

    Raises:
        HTTPException: 404 if the operation is not part of this proposal.
    """
    with db.connect() as conn:
        owner = queries.operation_proposal_id(conn, operation_id)
    if owner != proposal_id:
        raise HTTPException(404, f"operation {operation_id} is not part of proposal {proposal_id}")
    apply.review_operation(db, operation_id, body.decision, body.edited_payload)
    with db.connect() as conn:
        return _proposal(conn, proposal_id)


@router.post("/proposals/{proposal_id}/commit")
def commit(db: Engine, proposal_id: int) -> Committed:
    """Apply the accepted and edited operations in one transaction.

    Args:
        db: The engine.
        proposal_id: The proposal.

    Returns:
        What was written.
    """
    result = apply.commit_proposal(db, proposal_id)
    return Committed(
        commit_id=result.commit_id,
        applied_operation_ids=result.applied_operation_ids,
        entity_ids=result.entity_ids,
    )
