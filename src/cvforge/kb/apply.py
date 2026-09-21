"""THE ONLY WRITER. Every INSERT, UPDATE and DELETE in `src/cvforge/` lives here.

Invariant 2 (CLAUDE.md) and ADR-0006: this module is the single write path, and
`tests/unit/test_write_path_invariant.py` fails if any other module in `src/`
constructs a write. Its public surface is deliberately small, and fixed by
`test_apply_public_surface`:

- **Intake** (`record_source`, `record_evidence`) captures what was said or
  uploaded. These rows are records of input, not knowledge, so they are written
  at capture time (ADR-0009).
- **Review** (`record_proposal`, `review_operation`) stores proposed operations
  and the reviewer's decision on each one. Nothing here touches knowledge rows.
- **Commit** (`commit_proposal`) is the only path to `entity`, `edge` and
  `assertion`. It applies the accepted and edited operations of one proposal in
  one transaction, and writes at least one assertion for everything it creates
  (invariant 3).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from pydantic import JsonValue, ValidationError

from cvforge.kb import schema
from cvforge.kb.models import (
    COMMON_FIELDS,
    KIND_ATTRIBUTES,
    AddEdge,
    AttachEvidence,
    CreateEntity,
    EntityRef,
    MergeDuplicate,
    OpRef,
    ProposalDraft,
    SetState,
    UpdateField,
    normalize_name,
    parse_payload,
)
from cvforge.kb.vocab import (
    Classification,
    EntityKind,
    OpStatus,
    OpType,
    ProposalStatus,
    SourceKind,
    TargetKind,
)

AnyPayload = CreateEntity | UpdateField | AddEdge | AttachEvidence | MergeDuplicate | SetState
Decision = Literal["accept", "edit", "reject"]


class ApplyError(Exception):
    """Base class for every refusal raised by the write path."""


class NotFoundError(ApplyError):
    """A referenced proposal, operation, evidence row or target does not exist."""


class ProposalNotOpenError(ApplyError):
    """The proposal was already committed; it can be neither reviewed nor committed again."""


class OperationsPendingError(ApplyError):
    """At least one operation has not been reviewed yet (FR-09)."""


class InvalidEditError(ApplyError):
    """A reviewer's edit does not fit the operation it replaces."""


class UnsupportedOperationError(ApplyError):
    """The operation is valid but this version cannot apply it yet."""


@dataclass(frozen=True)
class CommitResult:
    """What a commit wrote.

    Attributes:
        commit_id: The `commit_log` row.
        applied_operation_ids: Operations applied, in `seq` order.
        entity_ids: For each applied `create_entity` seq, the entity it resolved to
            (a new row, or the existing one for `known`/`duplicate`).
    """

    commit_id: int
    applied_operation_ids: list[int]
    entity_ids: dict[int, int]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- intake -------------------------------------------------------------------


def record_source(
    engine: sa.Engine,
    kind: SourceKind,
    label: str,
    *,
    uri: str | None = None,
    content_hash: str | None = None,
    raw_text_path: str | None = None,
) -> int:
    """Record where input came from: a conversation, document, web page or manual entry.

    Args:
        engine: The knowledge-base engine.
        kind: The source kind.
        label: Human-readable label (conversation title, file name, page title).
        uri: Optional URI of the original.
        content_hash: Optional hash of the captured content.
        raw_text_path: Optional path of the extracted text under `data/`.

    Returns:
        The new source id.
    """
    with engine.begin() as conn:
        result = conn.execute(
            sa.insert(schema.source).values(
                kind=kind.value,
                label=label,
                uri=uri,
                content_hash=content_hash,
                captured_at=_now(),
                raw_text_path=raw_text_path,
            )
        )
        return _pk(result)


def record_evidence(engine: sa.Engine, source_id: int, locator: str, excerpt: str) -> int:
    """Record one citable span of a source (a chat message, a page range...).

    Args:
        engine: The knowledge-base engine.
        source_id: The source the span belongs to. Must exist (foreign key).
        locator: Where in the source, e.g. ``message:3`` or ``page:2 chars:10-80``.
        excerpt: The literal text of the span.

    Returns:
        The new evidence id.

    Raises:
        NotFoundError: If the source does not exist.
    """
    try:
        with engine.begin() as conn:
            result = conn.execute(
                sa.insert(schema.evidence).values(
                    source_id=source_id, locator=locator, excerpt=excerpt
                )
            )
            return _pk(result)
    except sa.exc.IntegrityError as error:
        raise NotFoundError(f"source {source_id} does not exist") from error


# --- review ---------------------------------------------------------------------


def record_proposal(engine: sa.Engine, draft: ProposalDraft) -> int:
    """Store a proposal and its operations, all `pending`, for review.

    Every operation must cite evidence that already exists: an operation with no
    source behind it never reaches review (FR-12).

    Args:
        engine: The knowledge-base engine.
        draft: The validated proposal.

    Returns:
        The new proposal id.

    Raises:
        NotFoundError: If the source or any cited evidence row does not exist.
    """
    with engine.begin() as conn:
        _require(conn, schema.source, draft.source_id, "source")
        for op in draft.operations:
            _require(conn, schema.evidence, op.payload.evidence_id, "evidence")
        proposal_id = _pk(
            conn.execute(
                sa.insert(schema.proposal).values(
                    origin=draft.origin.value,
                    source_id=draft.source_id,
                    status=ProposalStatus.OPEN.value,
                    summary=draft.summary,
                    created_at=_now(),
                )
            )
        )
        for op in sorted(draft.operations, key=lambda o: o.seq):
            conn.execute(
                sa.insert(schema.operation).values(
                    proposal_id=proposal_id,
                    seq=op.seq,
                    op_type=op.payload.op_type.value,
                    payload_json=op.payload.model_dump(mode="json"),
                    classification=op.classification.value,
                    target_kind=op.target_kind.value if op.target_kind else None,
                    target_id=op.target_id,
                    status=OpStatus.PENDING.value,
                    rationale=op.rationale,
                )
            )
        return proposal_id


def review_operation(
    engine: sa.Engine,
    operation_id: int,
    decision: Decision,
    edited_payload: Mapping[str, JsonValue] | None = None,
) -> None:
    """Accept, edit or reject one operation, independently of its siblings (FR-09).

    An edit keeps the original payload and stores the reviewer's version beside
    it in `edited_payload_json`; the commit applies the edited one.

    Args:
        engine: The knowledge-base engine.
        operation_id: The operation being reviewed.
        decision: ``accept``, ``edit`` or ``reject``.
        edited_payload: The replacement payload; required for ``edit`` only.

    Raises:
        NotFoundError: If the operation does not exist.
        ProposalNotOpenError: If its proposal was already committed.
        InvalidEditError: If an edit is missing, changes the operation type, or
            does not validate.
    """
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(schema.operation.c.op_type, schema.proposal.c.status)
            .join(schema.proposal, schema.proposal.c.id == schema.operation.c.proposal_id)
            .where(schema.operation.c.id == operation_id)
        ).one_or_none()
        if row is None:
            raise NotFoundError(f"operation {operation_id} does not exist")
        if row.status != ProposalStatus.OPEN:
            raise ProposalNotOpenError(f"operation {operation_id} belongs to a committed proposal")
        values: dict[str, Any] = {"edited_payload_json": None}
        if decision == "edit":
            values["edited_payload_json"] = _validated_edit(row.op_type, edited_payload)
            values["status"] = OpStatus.EDITED.value
        elif edited_payload is not None:
            raise InvalidEditError("an edited payload is only accepted with decision 'edit'")
        else:
            accepted = decision == "accept"
            values["status"] = (OpStatus.ACCEPTED if accepted else OpStatus.REJECTED).value
        conn.execute(
            sa.update(schema.operation)
            .where(schema.operation.c.id == operation_id)
            .values(**values)
        )


def _validated_edit(op_type: str, edited: Mapping[str, JsonValue] | None) -> dict[str, Any]:
    if edited is None:
        raise InvalidEditError("decision 'edit' requires an edited payload")
    try:
        payload = parse_payload(dict(edited))
    except ValidationError as error:
        raise InvalidEditError(f"edited payload is invalid: {error}") from error
    if payload.op_type != op_type:
        raise InvalidEditError(f"an edit cannot change {op_type} into {payload.op_type}")
    return payload.model_dump(mode="json")


# --- commit ---------------------------------------------------------------------


def commit_proposal(engine: sa.Engine, proposal_id: int) -> CommitResult:
    """Apply every accepted and edited operation of a proposal in ONE transaction (FR-10).

    Rejected operations are skipped. If any operation is still pending, nothing
    is applied. If any operation fails, the whole proposal rolls back and stays
    open for review.

    Args:
        engine: The knowledge-base engine.
        proposal_id: The proposal to commit.

    Returns:
        What was written.

    Raises:
        NotFoundError: If the proposal, or a target an operation names, is missing.
        ProposalNotOpenError: If the proposal was already committed.
        OperationsPendingError: If any operation has not been reviewed.
        UnsupportedOperationError: If an operation cannot be applied by this version.
        sqlalchemy.exc.IntegrityError: If the database rejects a row; nothing is kept.
    """
    with engine.begin() as conn:
        status = conn.execute(
            sa.select(schema.proposal.c.status).where(schema.proposal.c.id == proposal_id)
        ).scalar_one_or_none()
        if status is None:
            raise NotFoundError(f"proposal {proposal_id} does not exist")
        if status != ProposalStatus.OPEN:
            raise ProposalNotOpenError(f"proposal {proposal_id} was already committed")
        ops = conn.execute(
            sa.select(schema.operation)
            .where(schema.operation.c.proposal_id == proposal_id)
            .order_by(schema.operation.c.seq)
        ).all()
        pending = [op.seq for op in ops if op.status == OpStatus.PENDING]
        if pending:
            raise OperationsPendingError(f"operations {pending} are still pending review")

        committer = _Committer(conn)
        applied: list[int] = []
        for op in ops:
            if op.status in (OpStatus.ACCEPTED, OpStatus.EDITED):
                committer.apply(op)
                applied.append(op.id)

        now = _now()
        if applied:
            conn.execute(
                sa.update(schema.operation)
                .where(schema.operation.c.id.in_(applied))
                .values(status=OpStatus.APPLIED.value)
            )
        conn.execute(
            sa.update(schema.proposal)
            .where(schema.proposal.c.id == proposal_id)
            .values(status=ProposalStatus.COMMITTED.value, applied_at=now)
        )
        commit_id = _pk(
            conn.execute(
                sa.insert(schema.commit_log).values(
                    proposal_id=proposal_id, applied_at=now, operation_ids_json=applied
                )
            )
        )
        return CommitResult(commit_id, applied, dict(committer.entity_ids))


class _Committer:
    """Applies operations on one open connection. Private to the commit path."""

    def __init__(self, conn: sa.Connection) -> None:
        self.conn = conn
        self.entity_ids: dict[int, int] = {}

    def apply(self, op: sa.Row[Any]) -> None:
        payload = parse_payload(op.edited_payload_json or op.payload_json)
        classification = Classification(op.classification)
        if classification in (Classification.KNOWN, Classification.DUPLICATE):
            self._support(op, payload)
        elif isinstance(payload, CreateEntity):
            if classification is Classification.CONFLICT:
                raise UnsupportedOperationError("a create_entity cannot be a conflict")
            self.entity_ids[op.seq] = self._create_entity(payload)
        elif isinstance(payload, UpdateField):
            self._update_field(payload)
        elif isinstance(payload, AddEdge):
            self._add_or_replace_edge(payload, conflict_edge=_target_id(op, TargetKind.EDGE))
        elif isinstance(payload, AttachEvidence):
            self._require_target(payload.target_kind, payload.target_id)
            self._assert(payload.target_kind, payload.target_id, payload.field, None, payload)
        elif isinstance(payload, SetState):
            self._set_state(payload)
        else:
            raise UnsupportedOperationError(
                f"{OpType.MERGE_DUPLICATE} is applied from M1b onwards (ADR-0009)"
            )

    # known / duplicate: the fact is already recorded, so accepting it only adds
    # this evidence to the existing target (ADR-0009). No new entity or edge row.
    def _support(self, op: sa.Row[Any], payload: AnyPayload) -> None:
        kind = TargetKind(op.target_kind)
        self._require_target(kind, op.target_id)
        field, value = _field_and_value(payload)
        self._assert(kind, op.target_id, field, value, payload)
        if isinstance(payload, CreateEntity):
            self.entity_ids[op.seq] = op.target_id

    def _create_entity(self, payload: CreateEntity) -> int:
        now = _now()
        entity_id = _pk(
            self.conn.execute(
                sa.insert(schema.entity).values(
                    kind=payload.kind.value,
                    name=payload.name,
                    normalized_name=normalize_name(payload.name),
                    summary=payload.summary,
                    state=payload.state.value,
                    first_seen_at=now,
                    updated_at=now,
                )
            )
        )
        attributes = payload.typed_attributes()
        self.conn.execute(
            sa.insert(schema.KIND_TABLES[payload.kind]).values(id=entity_id, **attributes)
        )
        entity = TargetKind.ENTITY
        self._assert(entity, entity_id, None, None, payload)
        self._assert(entity, entity_id, "name", payload.name, payload)
        self._assert(entity, entity_id, "state", payload.state.value, payload)
        if payload.summary is not None:
            self._assert(entity, entity_id, "summary", payload.summary, payload)
        for field, value in payload.model_dump(mode="json")["attributes"].items():
            if value is not None:
                self._assert(entity, entity_id, field, value, payload)
        return entity_id

    def _update_field(self, payload: UpdateField) -> None:
        kind = self._entity_kind(payload.entity_id)
        now = _now()
        if payload.field in COMMON_FIELDS:
            values: dict[str, Any] = {payload.field: payload.value, "updated_at": now}
            if payload.field == "name":
                if not isinstance(payload.value, str) or not normalize_name(payload.value):
                    raise InvalidEditError("name must be a non-empty string")
                values["normalized_name"] = normalize_name(payload.value)
            self.conn.execute(
                sa.update(schema.entity)
                .where(schema.entity.c.id == payload.entity_id)
                .values(**values)
            )
        else:
            attributes = KIND_ATTRIBUTES[kind]
            if payload.field not in attributes.model_fields:
                raise InvalidEditError(f"{kind} has no field {payload.field!r}")
            typed = attributes.model_validate({payload.field: payload.value}).model_dump()
            table = schema.KIND_TABLES[kind]
            self.conn.execute(
                sa.update(table)
                .where(table.c.id == payload.entity_id)
                .values({payload.field: typed[payload.field]})
            )
            self.conn.execute(
                sa.update(schema.entity)
                .where(schema.entity.c.id == payload.entity_id)
                .values(updated_at=now)
            )
        self._assert(TargetKind.ENTITY, payload.entity_id, payload.field, payload.value, payload)

    def _add_or_replace_edge(self, payload: AddEdge, conflict_edge: int | None) -> None:
        src, dst = self._resolve(payload.src), self._resolve(payload.dst)
        columns = {
            "confidence": payload.confidence,
            "started_at": payload.started_at,
            "ended_at": payload.ended_at,
            "note": payload.note,
        }
        if conflict_edge is not None:
            self._require_target(TargetKind.EDGE, conflict_edge)
            self.conn.execute(
                sa.update(schema.edge).where(schema.edge.c.id == conflict_edge).values(**columns)
            )
            edge_id = conflict_edge
        else:
            edge_id = _pk(
                self.conn.execute(
                    sa.insert(schema.edge).values(
                        src_id=src, rel=payload.rel.value, dst_id=dst, **columns
                    )
                )
            )
        self._assert(TargetKind.EDGE, edge_id, None, None, payload)

    def _set_state(self, payload: SetState) -> None:
        entity_id = self._resolve(payload.entity)
        self._entity_kind(entity_id)
        self.conn.execute(
            sa.update(schema.entity)
            .where(schema.entity.c.id == entity_id)
            .values(state=payload.state.value, updated_at=_now())
        )
        self._assert(TargetKind.ENTITY, entity_id, "state", payload.state.value, payload)

    def _assert(
        self,
        target_kind: TargetKind,
        target_id: int,
        field: str | None,
        value: JsonValue,
        payload: AnyPayload,
    ) -> None:
        self.conn.execute(
            sa.insert(schema.assertion).values(
                target_kind=target_kind.value,
                target_id=target_id,
                field=field,
                value_json=value,
                evidence_id=payload.evidence_id,
                created_at=_now(),
            )
        )

    def _resolve(self, ref: EntityRef) -> int:
        if isinstance(ref, OpRef):
            if ref.op not in self.entity_ids:
                raise UnsupportedOperationError(
                    f"op {ref.op} was not applied, so nothing can refer to it"
                )
            return self.entity_ids[ref.op]
        self._require_target(TargetKind.ENTITY, ref)
        return ref

    def _entity_kind(self, entity_id: int) -> EntityKind:
        kind = self.conn.execute(
            sa.select(schema.entity.c.kind).where(schema.entity.c.id == entity_id)
        ).scalar_one_or_none()
        if kind is None:
            raise NotFoundError(f"entity {entity_id} does not exist")
        return EntityKind(kind)

    def _require_target(self, kind: TargetKind, target_id: int) -> None:
        table = schema.entity if kind is TargetKind.ENTITY else schema.edge
        _require(self.conn, table, target_id, kind.value)


def _field_and_value(payload: AnyPayload) -> tuple[str | None, JsonValue]:
    if isinstance(payload, UpdateField):
        return payload.field, payload.value
    if isinstance(payload, SetState):
        return "state", payload.state.value
    if isinstance(payload, AttachEvidence):
        return payload.field, None
    return None, None


def _target_id(op: sa.Row[Any], kind: TargetKind) -> int | None:
    if op.classification == Classification.CONFLICT and op.target_kind == kind:
        return int(op.target_id)
    return None


def _require(conn: sa.Connection, table: sa.Table, row_id: int, what: str) -> None:
    found = conn.execute(sa.select(table.c.id).where(table.c.id == row_id)).first()
    if found is None:
        raise NotFoundError(f"{what} {row_id} does not exist")


def _pk(result: sa.CursorResult[Any]) -> int:
    return int(result.inserted_primary_key[0])  # type: ignore[index]
