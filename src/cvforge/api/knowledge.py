"""Read-only knowledge endpoints: entities, their edges, and provenance (FR-03, FR-04)."""

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException

from cvforge.api.errors import connection
from cvforge.kb import queries
from cvforge.kb.vocab import EntityKind, KnowledgeState, TargetKind

router = APIRouter(tags=["knowledge"])
Conn = Annotated[sa.Connection, Depends(connection)]


@router.get("/entities")
def list_entities(
    conn: Conn, kind: EntityKind | None = None, state: KnowledgeState | None = None
) -> list[queries.EntityRecord]:
    """List entities, optionally filtered by kind and knowledge state.

    Args:
        conn: Read connection.
        kind: Only this kind.
        state: Only this knowledge state.

    Returns:
        Matching entities.
    """
    return queries.list_entities(conn, kind=kind, state=state)


@router.get("/entities/{entity_id}")
def get_entity(conn: Conn, entity_id: int) -> queries.EntityRecord:
    """Return one entity with its kind-specific attributes.

    Args:
        conn: Read connection.
        entity_id: The entity id.

    Returns:
        The entity.

    Raises:
        HTTPException: 404 if it does not exist.
    """
    found = queries.get_entity(conn, entity_id)
    if found is None:
        raise HTTPException(404, f"entity {entity_id} does not exist")
    return found


@router.get("/entities/{entity_id}/edges")
def entity_edges(conn: Conn, entity_id: int) -> list[queries.EdgeRecord]:
    """Return every edge touching an entity.

    Args:
        conn: Read connection.
        entity_id: The entity id.

    Returns:
        The edges.
    """
    return queries.neighbours(conn, entity_id)


@router.get("/provenance/{target_kind}/{target_id}")
def provenance(
    conn: Conn, target_kind: TargetKind, target_id: int
) -> list[queries.ProvenanceRecord]:
    """Show where a stored fact came from: source kind, locator and excerpt (FR-03).

    Args:
        conn: Read connection.
        target_kind: ``entity`` or ``edge``.
        target_id: Its id.

    Returns:
        One record per assertion.

    Raises:
        HTTPException: 404 if nothing is asserted about that target.
    """
    records = queries.provenance(conn, target_kind, target_id)
    if not records:
        raise HTTPException(404, f"no assertions about {target_kind} {target_id}")
    return records
