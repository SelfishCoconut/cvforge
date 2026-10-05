"""Review endpoints: read a proposal, decide each operation, commit (FR-09, FR-10).

There is no endpoint that creates entities, edges or assertions directly: the
only route to them is committing a reviewed proposal.
"""

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, JsonValue

from cvforge.api.errors import connection, engine
from cvforge.kb import apply, queries
from cvforge.kb.embeddings import EmbeddingProvider, index_entities

router = APIRouter(tags=["review"])
Conn = Annotated[sa.Connection, Depends(connection)]
Engine = Annotated[sa.Engine, Depends(engine)]


def _embedder(request: Request) -> EmbeddingProvider | None:
    """FastAPI dependency: the embedder the app was built with, or None.

    Args:
        request: The incoming request.

    Returns:
        The embedder, or None if commit-time indexing is disabled.
    """
    result: EmbeddingProvider | None = request.app.state.embedder
    return result


Embedder = Annotated[EmbeddingProvider | None, Depends(_embedder)]


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
        index_pending: Entity ids the similarity index could not embed yet (the
            embedder was unavailable). The commit still happened; only the
            search index is behind — `reindex_missing` catches these up later.
    """

    commit_id: int
    applied_operation_ids: list[int]
    entity_ids: dict[int, int]
    index_pending: list[int] = []


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

    Raises:
        HTTPException: 404 if the proposal does not exist.
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
        NotFoundError: Mapped to 404 if the operation does not exist.
        ProposalNotOpenError: Mapped to 409 if the proposal was already committed.
        InvalidEditError: Mapped to 422 if an edit is missing, changes the
            operation type, does not validate, or accompanies accept/reject.
    """
    with db.connect() as conn:
        owner = queries.operation_proposal_id(conn, operation_id)
    if owner != proposal_id:
        raise HTTPException(404, f"operation {operation_id} is not part of proposal {proposal_id}")
    apply.review_operation(db, operation_id, body.decision, body.edited_payload)
    with db.connect() as conn:
        return _proposal(conn, proposal_id)


@router.post("/proposals/{proposal_id}/commit")
def commit(db: Engine, embedder: Embedder, proposal_id: int) -> Committed:
    """Apply the accepted and edited operations in one transaction.

    New entities, and existing ones whose name or summary just changed, are
    indexed for similarity search right after (never inside the write
    transaction — D-D). A failed embedding call never fails the commit: the
    affected ids come back as `index_pending` instead.

    Args:
        db: The engine.
        embedder: What indexes new and changed entities; `None` skips indexing.
        proposal_id: The proposal.

    Returns:
        What was written.

    Raises:
        NotFoundError: Mapped to 404 if the proposal, or a target an operation
            names, does not exist.
        ProposalNotOpenError: Mapped to 409 if the proposal was already committed.
        OperationsPendingError: Mapped to 409 if any operation is still pending.
        UnsupportedOperationError: Mapped to 422 if an operation cannot be
            applied by this version (`merge_duplicate`, until M1b).
        sqlalchemy.exc.IntegrityError: Mapped to 409; the database rejected a
            row and nothing was written.
    """
    result = apply.commit_proposal(db, proposal_id)
    index_pending: list[int] = []
    to_index = sorted({*result.entity_ids.values(), *result.reindex_ids})
    if embedder is not None and to_index:
        index_pending = index_entities(db, embedder, to_index)
    return Committed(
        commit_id=result.commit_id,
        applied_operation_ids=result.applied_operation_ids,
        entity_ids=result.entity_ids,
        index_pending=index_pending,
    )
