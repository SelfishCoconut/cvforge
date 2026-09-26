"""Deterministic classification of proposed operations (FR-08, ADR-0009).

The model proposes; the database decides what is already known. So an agent's
raw candidate is classified HERE, by comparing it with stored rows, never by
asking the model. The four values mean exactly this (ADR-0009):

- `new`: nothing stored covers it. Accepting creates or changes rows.
- `known`: the same thing is already recorded. For entities that means the same
  kind and normalized name, and only for kinds where the name is the identity.
  Accepting adds this evidence to the existing record and creates nothing.
- `duplicate`: a DIFFERENTLY named record probably is the same thing, found by
  similarity search. Accepting links to that record in the same way. There is no
  similarity search until M1b, so today only an injected `SimilarFinder` can
  produce this.
- `conflict`: the same field or edge is recorded with a DIFFERENT value.
  Accepting replaces the stored value, and keeps the old assertion as history.
"""

from collections.abc import Callable
from dataclasses import dataclass

import sqlalchemy as sa

from cvforge.kb import queries, schema
from cvforge.kb.models import (
    COMMON_FIELDS,
    AddEdge,
    CreateEntity,
    OpRef,
    SetState,
    UpdateField,
)
from cvforge.kb.vocab import Classification, EntityKind, TargetKind

# Kinds whose name identifies the thing. Two roles called "Software Engineer",
# or two achievements with the same headline, are routinely different facts, so
# a name match proves nothing for them.
NAME_IS_IDENTITY = frozenset(
    {EntityKind.SKILL, EntityKind.ORGANIZATION, EntityKind.PROJECT, EntityKind.CREDENTIAL}
)

SimilarFinder = Callable[[EntityKind, str], int | None]
"""Return the id of a differently-named entity that is probably the same, or None."""


@dataclass(frozen=True)
class Verdict:
    """A classification and, unless `new`, the record it concerns."""

    classification: Classification
    target_kind: TargetKind | None = None
    target_id: int | None = None


NEW = Verdict(Classification.NEW)


def classify(
    conn: sa.Connection,
    payload: object,
    *,
    similar: SimilarFinder | None = None,
) -> Verdict:
    """Classify one proposed operation against what is stored.

    Args:
        conn: An open connection.
        payload: A typed operation payload.
        similar: Optional similarity lookup; the source of `duplicate`.

    Returns:
        The verdict. Operation types with no stored counterpart are `new`.
    """
    if isinstance(payload, CreateEntity):
        return _create(conn, payload, similar)
    if isinstance(payload, UpdateField):
        return _update(conn, payload)
    if isinstance(payload, AddEdge):
        return _edge(conn, payload)
    if isinstance(payload, SetState):
        return _state(conn, payload)
    return NEW


def _create(conn: sa.Connection, payload: CreateEntity, similar: SimilarFinder | None) -> Verdict:
    if payload.kind in NAME_IS_IDENTITY:
        matches = queries.find_by_name(conn, payload.kind, payload.name)
        if matches:
            return Verdict(Classification.KNOWN, TargetKind.ENTITY, matches[0])
    if similar is not None:
        match = similar(payload.kind, payload.name)
        if match is not None:
            return Verdict(Classification.DUPLICATE, TargetKind.ENTITY, match)
    return NEW


def _update(conn: sa.Connection, payload: UpdateField) -> Verdict:
    entity = queries.get_entity(conn, payload.entity_id)
    if entity is None:
        return NEW  # the commit refuses a missing target; classification does not guess
    if payload.field in COMMON_FIELDS:
        current = getattr(entity, payload.field)
    else:
        current = entity.attributes.get(payload.field)
    if current is None:
        return NEW
    if _same(current, payload.value):
        return Verdict(Classification.KNOWN, TargetKind.ENTITY, entity.id)
    return Verdict(Classification.CONFLICT, TargetKind.ENTITY, entity.id)


def _edge(conn: sa.Connection, payload: AddEdge) -> Verdict:
    if isinstance(payload.src, OpRef) or isinstance(payload.dst, OpRef):
        return NEW  # one end does not exist yet, so neither can the edge
    stored = queries.find_edge(conn, payload.src, payload.rel.value, payload.dst)
    if stored is None:
        return NEW
    proposed = (payload.started_at, payload.ended_at)
    recorded = (stored.started_at, stored.ended_at)
    differs = any(
        p is not None and r is not None and p != r for p, r in zip(proposed, recorded, strict=True)
    )
    classification = Classification.CONFLICT if differs else Classification.KNOWN
    return Verdict(classification, TargetKind.EDGE, stored.id)


def _state(conn: sa.Connection, payload: SetState) -> Verdict:
    if isinstance(payload.entity, OpRef):
        return NEW
    state = conn.execute(
        sa.select(schema.entity.c.state).where(schema.entity.c.id == payload.entity)
    ).scalar_one_or_none()
    if state == payload.state.value:
        return Verdict(Classification.KNOWN, TargetKind.ENTITY, payload.entity)
    return NEW


def _same(current: object, proposed: object) -> bool:
    return str(current).strip().casefold() == str(proposed).strip().casefold()
