"""Read-only knowledge-base tools offered to agents (FR-06).

Every function here only reads. Agents have no write tools (invariant 2): what
they learn they return as a proposal, and a human reviews it (invariant 4).
"""

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from pydantic_ai import RunContext

from cvforge.kb import embeddings, queries
from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider
from cvforge.kb.models import normalize_name
from cvforge.kb.vocab import EntityKind

READ_TOOLS = frozenset({"search_entities", "get_entity", "neighbours", "find_similar"})
"""The only tool names any registered agent may offer the model."""

_MAX_RESULTS = 20


@dataclass
class KbDeps:
    """What a tool may read: the database and, if configured, an embedder."""

    engine: sa.Engine
    embedder: EmbeddingProvider | None


def search_entities(
    ctx: RunContext[KbDeps], query: str, kind: EntityKind | None = None
) -> list[dict[str, Any]]:
    """Find existing entities whose name contains `query` (case-insensitive).

    Args:
        ctx: The run context.
        query: Text to look for in entity names.
        kind: Only entities of this kind.

    Returns:
        Up to 20 matches with id, kind, name and summary.
    """
    needle = normalize_name(query)
    with ctx.deps.engine.connect() as conn:
        found = queries.list_entities(conn, kind=kind)
    return [
        {"id": e.id, "kind": e.kind, "name": e.name, "summary": e.summary}
        for e in found
        if needle in e.normalized_name
    ][:_MAX_RESULTS]


def get_entity(ctx: RunContext[KbDeps], entity_id: int) -> dict[str, Any] | None:
    """Return one existing entity with its attributes, or None.

    Args:
        ctx: The run context.
        entity_id: The entity id.

    Returns:
        The entity, or None if there is no such id.
    """
    with ctx.deps.engine.connect() as conn:
        record = queries.get_entity(conn, entity_id)
    if record is None:
        return None
    return {
        "id": record.id,
        "kind": record.kind,
        "name": record.name,
        "summary": record.summary,
        "state": record.state,
        "attributes": {k: str(v) for k, v in record.attributes.items() if v is not None},
    }


def neighbours(ctx: RunContext[KbDeps], entity_id: int) -> list[dict[str, Any]]:
    """Return the relationships touching an existing entity.

    Args:
        ctx: The run context.
        entity_id: The entity id.

    Returns:
        Edges with src, rel and dst entity ids.
    """
    with ctx.deps.engine.connect() as conn:
        edges = queries.neighbours(conn, entity_id)
    return [{"src": e.src_id, "rel": e.rel, "dst": e.dst_id} for e in edges][:_MAX_RESULTS]


def find_similar(
    ctx: RunContext[KbDeps], text: str, kind: EntityKind | None = None
) -> list[dict[str, Any]]:
    """Find existing entities semantically close to `text`.

    Args:
        ctx: The run context.
        text: A candidate name or description.
        kind: Only entities of this kind.

    Returns:
        Hits with entity id, name and score; empty when similarity is unavailable.
    """
    embedder = ctx.deps.embedder
    if embedder is None:
        return []
    try:
        hits = embeddings.find_similar(ctx.deps.engine, embedder, text, kind=kind)
    except EmbeddingError:
        return []
    return [{"id": h.entity_id, "name": h.name, "score": round(h.score, 3)} for h in hits]


TOOLS = (search_entities, get_entity, neighbours, find_similar)
