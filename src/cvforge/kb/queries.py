"""Read-only access to the knowledge base (ADR-0006).

Every function here takes an open `Connection` and returns plain frozen
dataclasses, never live database-bound rows. Nothing in this module writes;
joined-table inheritance is spelled out as explicit joins.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from cvforge.kb import schema
from cvforge.kb.models import normalize_name
from cvforge.kb.vocab import EntityKind, KnowledgeState, TargetKind


@dataclass(frozen=True)
class EntityRecord:
    """One entity with its kind-specific attributes."""

    id: int
    kind: EntityKind
    name: str
    normalized_name: str
    summary: str | None
    state: KnowledgeState
    first_seen_at: datetime
    updated_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeRecord:
    """One typed relationship."""

    id: int
    src_id: int
    rel: str
    dst_id: int
    confidence: float | None
    started_at: Any
    ended_at: Any
    note: str | None


@dataclass(frozen=True)
class ProvenanceRecord:
    """One assertion resolved back to the literal evidence it cites (FR-03)."""

    assertion_id: int
    field: str | None
    value: Any
    source_id: int
    source_kind: str
    source_label: str
    locator: str
    excerpt: str


@dataclass(frozen=True)
class OperationRecord:
    """One operation of a proposal, with its review state."""

    id: int
    seq: int
    op_type: str
    payload: dict[str, Any]
    classification: str
    target_kind: str | None
    target_id: int | None
    status: str
    edited_payload: dict[str, Any] | None
    rationale: str | None


@dataclass(frozen=True)
class ProposalRecord:
    """A proposal and its operations in `seq` order."""

    id: int
    origin: str
    source_id: int
    status: str
    summary: str
    created_at: datetime
    applied_at: datetime | None
    operations: list[OperationRecord]


@dataclass(frozen=True)
class OrphanReport:
    """Violations of invariant 3. Every list is empty in a healthy database."""

    entities_without_assertion: list[int]
    edges_without_assertion: list[int]
    assertions_without_target: list[int]

    @property
    def clean(self) -> bool:
        """True when there are no violations at all."""
        return not (
            self.entities_without_assertion
            or self.edges_without_assertion
            or self.assertions_without_target
        )


_ENTITY_COLUMNS = [c for c in schema.entity.c]


def _entity(row: sa.Row[Any], attributes: dict[str, Any] | None = None) -> EntityRecord:
    return EntityRecord(
        id=row.id,
        kind=EntityKind(row.kind),
        name=row.name,
        normalized_name=row.normalized_name,
        summary=row.summary,
        state=KnowledgeState(row.state),
        first_seen_at=row.first_seen_at,
        updated_at=row.updated_at,
        attributes=attributes or {},
    )


def get_entity(conn: sa.Connection, entity_id: int) -> EntityRecord | None:
    """Return one entity with its kind-specific attributes, or None.

    Args:
        conn: An open connection.
        entity_id: The entity id.

    Returns:
        The entity, or None if it does not exist.
    """
    row = conn.execute(sa.select(schema.entity).where(schema.entity.c.id == entity_id)).first()
    if row is None:
        return None
    table = schema.KIND_TABLES[EntityKind(row.kind)]
    child = conn.execute(sa.select(table).where(table.c.id == entity_id)).first()
    attributes = {k: v for k, v in child._mapping.items() if k != "id"} if child else {}
    return _entity(row, attributes)


def list_entities(
    conn: sa.Connection,
    *,
    kind: EntityKind | None = None,
    state: KnowledgeState | None = None,
) -> list[EntityRecord]:
    """List entities, optionally filtered by kind and knowledge state (FR-04).

    Attributes are not loaded; use `get_entity` for one entity's full record.

    Args:
        conn: An open connection.
        kind: Only entities of this kind.
        state: Only entities in this knowledge state.

    Returns:
        Matching entities ordered by id.
    """
    query = sa.select(schema.entity).order_by(schema.entity.c.id)
    if kind is not None:
        query = query.where(schema.entity.c.kind == kind.value)
    if state is not None:
        query = query.where(schema.entity.c.state == state.value)
    return [_entity(row) for row in conn.execute(query)]


def find_by_name(conn: sa.Connection, kind: EntityKind, name: str) -> list[int]:
    """Return the ids of entities of `kind` whose normalized name equals `name`'s.

    Args:
        conn: An open connection.
        kind: The entity kind.
        name: A display name; it is normalized before comparing.

    Returns:
        Matching entity ids, ordered.
    """
    query = (
        sa.select(schema.entity.c.id)
        .where(schema.entity.c.kind == kind.value)
        .where(schema.entity.c.normalized_name == normalize_name(name))
        .order_by(schema.entity.c.id)
    )
    return list(conn.execute(query).scalars())


def _edge(row: sa.Row[Any]) -> EdgeRecord:
    return EdgeRecord(
        id=row.id,
        src_id=row.src_id,
        rel=row.rel,
        dst_id=row.dst_id,
        confidence=row.confidence,
        started_at=row.started_at,
        ended_at=row.ended_at,
        note=row.note,
    )


def find_edge(conn: sa.Connection, src_id: int, rel: str, dst_id: int) -> EdgeRecord | None:
    """Return the edge with exactly this (src, rel, dst), or None.

    Args:
        conn: An open connection.
        src_id: Source entity id.
        rel: Relationship value.
        dst_id: Destination entity id.

    Returns:
        The edge, or None.
    """
    e = schema.edge.c
    row = conn.execute(
        sa.select(schema.edge).where(e.src_id == src_id, e.rel == rel, e.dst_id == dst_id)
    ).first()
    return _edge(row) if row else None


def neighbours(conn: sa.Connection, entity_id: int) -> list[EdgeRecord]:
    """Return every edge touching an entity, in either direction.

    Args:
        conn: An open connection.
        entity_id: The entity id.

    Returns:
        Edges ordered by id.
    """
    e = schema.edge.c
    query = (
        sa.select(schema.edge)
        .where(sa.or_(e.src_id == entity_id, e.dst_id == entity_id))
        .order_by(e.id)
    )
    return [_edge(row) for row in conn.execute(query)]


def provenance(
    conn: sa.Connection, target_kind: TargetKind, target_id: int
) -> list[ProvenanceRecord]:
    """Resolve every assertion about a thing back to its source and excerpt (FR-03, FR-12).

    Args:
        conn: An open connection.
        target_kind: ``entity`` or ``edge``.
        target_id: The entity or edge id.

    Returns:
        One record per assertion, oldest first.
    """
    a, ev, src = schema.assertion.c, schema.evidence.c, schema.source.c
    query = (
        sa.select(
            a.id,
            a.field,
            a.value_json,
            src.id.label("source_id"),
            src.kind,
            src.label,
            ev.locator,
            ev.excerpt,
        )
        .select_from(
            schema.assertion.join(schema.evidence, ev.id == a.evidence_id).join(
                schema.source, src.id == ev.source_id
            )
        )
        .where(a.target_kind == target_kind.value, a.target_id == target_id)
        .order_by(a.id)
    )
    return [
        ProvenanceRecord(
            assertion_id=row.id,
            field=row.field,
            value=row.value_json,
            source_id=row.source_id,
            source_kind=row.kind,
            source_label=row.label,
            locator=row.locator,
            excerpt=row.excerpt,
        )
        for row in conn.execute(query)
    ]


def get_proposal(conn: sa.Connection, proposal_id: int) -> ProposalRecord | None:
    """Return a proposal with its operations, or None.

    Args:
        conn: An open connection.
        proposal_id: The proposal id.

    Returns:
        The proposal, or None if it does not exist.
    """
    row = conn.execute(
        sa.select(schema.proposal).where(schema.proposal.c.id == proposal_id)
    ).first()
    if row is None:
        return None
    ops = conn.execute(
        sa.select(schema.operation)
        .where(schema.operation.c.proposal_id == proposal_id)
        .order_by(schema.operation.c.seq)
    )
    return ProposalRecord(
        id=row.id,
        origin=row.origin,
        source_id=row.source_id,
        status=row.status,
        summary=row.summary,
        created_at=row.created_at,
        applied_at=row.applied_at,
        operations=[
            OperationRecord(
                id=op.id,
                seq=op.seq,
                op_type=op.op_type,
                payload=op.payload_json,
                classification=op.classification,
                target_kind=op.target_kind,
                target_id=op.target_id,
                status=op.status,
                edited_payload=op.edited_payload_json,
                rationale=op.rationale,
            )
            for op in ops
        ],
    )


def operation_proposal_id(conn: sa.Connection, operation_id: int) -> int | None:
    """Return the proposal an operation belongs to, or None if it does not exist.

    Args:
        conn: An open connection.
        operation_id: The operation id.

    Returns:
        The proposal id, or None.
    """
    query = sa.select(schema.operation.c.proposal_id).where(schema.operation.c.id == operation_id)
    return conn.execute(query).scalar_one_or_none()


def orphans(conn: sa.Connection) -> OrphanReport:
    """Find every violation of invariant 3 (FR-03).

    Args:
        conn: An open connection.

    Returns:
        Entities and edges with no assertion, and assertions whose target is gone.
    """
    a = schema.assertion.c

    def unasserted(table: sa.Table, kind: TargetKind) -> list[int]:
        has = sa.select(a.id).where(a.target_kind == kind.value, a.target_id == table.c.id)
        query = sa.select(table.c.id).where(~has.exists()).order_by(table.c.id)
        return list(conn.execute(query).scalars())

    def dangling(table: sa.Table, kind: TargetKind) -> list[int]:
        exists = sa.select(table.c.id).where(table.c.id == a.target_id)
        query = sa.select(a.id).where(a.target_kind == kind.value, ~exists.exists())
        return list(conn.execute(query).scalars())

    return OrphanReport(
        entities_without_assertion=unasserted(schema.entity, TargetKind.ENTITY),
        edges_without_assertion=unasserted(schema.edge, TargetKind.EDGE),
        assertions_without_target=sorted(
            dangling(schema.entity, TargetKind.ENTITY) + dangling(schema.edge, TargetKind.EDGE)
        ),
    )


def table_counts(conn: sa.Connection) -> dict[str, int]:
    """Count the rows of every knowledge and provenance table (NFR-09 export check).

    Args:
        conn: An open connection.

    Returns:
        Table name to row count.
    """
    names = ["entity", "edge", "assertion", "source", "evidence", "proposal", "operation"]
    return {
        name: conn.execute(
            sa.select(sa.func.count()).select_from(schema.metadata.tables[name])
        ).scalar_one()
        for name in names
    }
