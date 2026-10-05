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

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import sqlalchemy as sa
from pydantic import JsonValue, ValidationError

from cvforge.kb import schema
from cvforge.kb.classify import NAME_IS_IDENTITY, NEW, SimilarFinder, Verdict, classify
from cvforge.kb.models import (
    COMMON_FIELDS,
    KIND_ATTRIBUTES,
    AddEdge,
    AttachEvidence,
    CreateEntity,
    EntityRef,
    MergeDuplicate,
    OpRef,
    ProposalInput,
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
EMBEDDED_FIELDS = frozenset({"name", "summary"})
"""The entity fields the similarity index embeds (`kb/embeddings.py`)."""


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


class StaleClassificationError(ApplyError):
    """A stored classification no longer describes what is in the database."""


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
        reindex_ids: Existing entities whose `name` or `summary` an applied
            `update_field` changed, so their similarity vectors are now stale.
            Not part of the HTTP response; the commit route re-embeds them.
    """

    commit_id: int
    applied_operation_ids: list[int]
    entity_ids: dict[int, int]
    reindex_ids: list[int]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@contextmanager
def _write_transaction(engine: sa.Engine) -> Iterator[sa.Connection]:
    """Open a transaction that holds SQLite's write lock before anything is read.

    pysqlite begins a transaction lazily, just before the first INSERT, UPDATE or
    DELETE. A plain `engine.begin()` therefore runs its checks (is the proposal
    still open? which operations are pending?) outside any lock and then writes
    on what it read, so two requests can pass the same check and both write: a
    proposal committed twice, or a reject landing after the commit it should have
    prevented. `BEGIN IMMEDIATE` takes the lock first. The second request waits,
    then reads the state the first one left behind.

    Args:
        engine: The knowledge-base engine.

    Yields:
        A connection inside the transaction. It is committed when the block ends
        and rolled back if the block raises.
    """
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()


def _json(value: date | float | str | None) -> JsonValue:
    """Render a column value the way an assertion's `value_json` stores it."""
    return value.isoformat() if isinstance(value, date) else value


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
        ValueError: If the locator or the excerpt is blank. A span that cites
            nothing satisfies invariant 3 in letter and not in spirit.
    """
    if not locator.strip() or not excerpt.strip():
        raise ValueError("evidence needs a locator and an excerpt; both must be non-blank")
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


def record_proposal(
    engine: sa.Engine, draft: ProposalInput, *, similar: SimilarFinder | None = None
) -> int:
    """Classify a proposal against the database, then store it, all `pending`.

    The caller supplies operations only; the classification and the target are
    computed here from stored rows (ADR-0009), so no intake can mislabel one.
    Similarity may embed text over the network, so it runs first, on a plain
    read connection and before any lock is taken. The write phase then
    re-classifies without it against the locked state, because the database may
    have moved in between.

    Every operation must cite evidence that already exists: an operation with no
    source behind it never reaches review (FR-12).

    Args:
        engine: The knowledge-base engine.
        draft: The validated proposal, without classifications.
        similar: Optional similarity lookup, the source of `duplicate`. An
            exception it raises propagates and nothing is stored.

    Returns:
        The new proposal id.

    Raises:
        NotFoundError: If the source or any cited evidence row does not exist.
    """
    with engine.connect() as conn:
        first = {op.seq: classify(conn, op.payload, similar=similar) for op in draft.operations}
    with _write_transaction(engine) as conn:
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
            verdict = _settled(first[op.seq], classify(conn, op.payload))
            conn.execute(
                sa.insert(schema.operation).values(
                    proposal_id=proposal_id,
                    seq=op.seq,
                    op_type=op.payload.op_type.value,
                    payload_json=op.payload.model_dump(mode="json"),
                    classification=verdict.classification.value,
                    target_kind=verdict.target_kind.value if verdict.target_kind else None,
                    target_id=verdict.target_id,
                    status=OpStatus.PENDING.value,
                    rationale=op.rationale,
                )
            )
        return proposal_id


def _settled(unlocked: Verdict, locked: Verdict) -> Verdict:
    """Prefer the locked answer: the database moved. Keep a `duplicate` it cannot re-derive."""
    if unlocked.classification is Classification.DUPLICATE and locked is NEW:
        return unlocked  # similarity needs I/O, which is not allowed under the lock
    return locked


def review_operation(
    engine: sa.Engine,
    operation_id: int,
    decision: Decision,
    edited_payload: Mapping[str, JsonValue] | None = None,
) -> None:
    """Accept, edit or reject one operation, independently of its siblings (FR-09).

    An edit keeps the original payload and stores the reviewer's version beside
    it in `edited_payload_json`; the commit applies the edited one. Each decision
    replaces the previous one, so accepting or rejecting an operation discards an
    earlier edit of it. An `edited` operation is already approved: to approve it
    as edited there is nothing more to do.

    The whole review runs under the write lock (`_write_transaction`), so it
    cannot land between a commit's checks and its writes.

    Args:
        engine: The knowledge-base engine.
        operation_id: The operation being reviewed.
        decision: ``accept``, ``edit`` or ``reject``.
        edited_payload: The replacement payload; required for ``edit`` only.

    Raises:
        NotFoundError: If the operation does not exist.
        ProposalNotOpenError: If its proposal was already committed.
        InvalidEditError: If an edit is missing, changes the operation type, or
            does not validate, or if an edited payload accompanies accept or reject.
    """
    with _write_transaction(engine) as conn:
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
            values["edited_payload_json"] = _validated_edit(conn, row.op_type, edited_payload)
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


def _validated_edit(
    conn: sa.Connection, op_type: str, edited: Mapping[str, JsonValue] | None
) -> dict[str, Any]:
    if edited is None:
        raise InvalidEditError("decision 'edit' requires an edited payload")
    try:
        payload = parse_payload(dict(edited))
    except ValidationError as error:
        raise InvalidEditError(f"edited payload is invalid: {error}") from error
    if payload.op_type != op_type:
        raise InvalidEditError(f"an edit cannot change {op_type} into {payload.op_type}")
    # An edit may change what is cited, so it needs the same check `record_proposal`
    # applies to the original: never rely on the foreign key alone for evidence.
    _require(conn, schema.evidence, payload.evidence_id, "evidence")
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
        RuntimeError: If the engine does not enforce foreign keys. Commit relies on
            them for the last line of defence on evidence and targets, so it
            refuses to run without them; build the engine with `kb.db.make_engine`.
        sqlalchemy.exc.IntegrityError: If the database rejects a row; nothing is kept.
    """
    with _write_transaction(engine) as conn:
        if conn.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1:
            raise RuntimeError(
                "foreign-key enforcement is off, so commit refuses to run; "
                "build the engine with cvforge.kb.db.make_engine"
            )
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
        return CommitResult(
            commit_id, applied, dict(committer.entity_ids), sorted(committer.reindex_ids)
        )


class _Committer:
    """Applies operations on one open connection. Private to the commit path."""

    def __init__(self, conn: sa.Connection) -> None:
        self.conn = conn
        self.entity_ids: dict[int, int] = {}
        self.reindex_ids: set[int] = set()

    def apply(self, op: sa.Row[Any]) -> None:
        payload = parse_payload(op.edited_payload_json or op.payload_json)
        classification = Classification(op.classification)
        if classification is not Classification.NEW:
            self._recheck(op, payload, classification)
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

    # A classification was computed when the proposal was recorded; the database may
    # have changed since. A target that is gone is NotFound; one that no longer
    # matches what the operation says is stale, and the whole commit rolls back.
    def _recheck(
        self, op: sa.Row[Any], payload: AnyPayload, classification: Classification
    ) -> None:
        kind = TargetKind(op.target_kind)
        self._require_target(kind, op.target_id)
        if not self._still_matches(kind, op.target_id, payload, classification):
            raise StaleClassificationError(
                f"operation {op.seq} was classified {classification} against {kind} "
                f"{op.target_id}, which no longer matches it; record the proposal again"
            )

    def _still_matches(
        self, kind: TargetKind, target_id: int, payload: AnyPayload, classification: Classification
    ) -> bool:
        if isinstance(payload, CreateEntity):
            return self._entity_matches(kind, target_id, payload, classification)
        if isinstance(payload, UpdateField):
            return (kind, target_id) == (TargetKind.ENTITY, payload.entity_id)
        if isinstance(payload, SetState):
            return (kind, target_id) == (TargetKind.ENTITY, payload.entity)
        if isinstance(payload, AddEdge):
            return kind is TargetKind.EDGE and self._edge_matches(target_id, payload)
        return True

    def _entity_matches(
        self,
        kind: TargetKind,
        target_id: int,
        payload: CreateEntity,
        classification: Classification,
    ) -> bool:
        if kind is not TargetKind.ENTITY:
            return False
        row = self.conn.execute(
            sa.select(schema.entity.c.kind, schema.entity.c.normalized_name).where(
                schema.entity.c.id == target_id
            )
        ).one()
        if row.kind != payload.kind.value:
            return False
        if classification is Classification.KNOWN and payload.kind in NAME_IS_IDENTITY:
            return bool(row.normalized_name == normalize_name(payload.name))
        return True

    def _edge_matches(self, edge_id: int, payload: AddEdge) -> bool:
        row = self.conn.execute(
            sa.select(schema.edge.c.src_id, schema.edge.c.rel, schema.edge.c.dst_id).where(
                schema.edge.c.id == edge_id
            )
        ).one()
        return (row.src_id, row.rel, row.dst_id) == (payload.src, payload.rel.value, payload.dst)

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
        if payload.field in EMBEDDED_FIELDS:
            self.reindex_ids.add(payload.entity_id)
        self._assert(TargetKind.ENTITY, payload.entity_id, payload.field, payload.value, payload)

    def _add_or_replace_edge(self, payload: AddEdge, conflict_edge: int | None) -> None:
        if conflict_edge is not None:
            self._revise_edge(payload, conflict_edge)
            return
        src, dst = self._resolve(payload.src), self._resolve(payload.dst)
        edge_id = _pk(
            self.conn.execute(
                sa.insert(schema.edge).values(
                    src_id=src,
                    rel=payload.rel.value,
                    dst_id=dst,
                    confidence=payload.confidence,
                    started_at=payload.started_at,
                    ended_at=payload.ended_at,
                    note=payload.note,
                )
            )
        )
        self._assert(TargetKind.EDGE, edge_id, None, None, payload)

    def _revise_edge(self, payload: AddEdge, edge_id: int) -> None:
        """Apply a `conflict` to a stored edge, changing only what the payload states.

        A payload that contests one date must not erase the confidence, the other
        date or the note it says nothing about. Each changed column gets its own
        assertion carrying the new value, so the old assertions stay as history and
        the change is recoverable from provenance alone.
        """
        self._require_target(TargetKind.EDGE, edge_id)
        stated = {
            name: value
            for name, value in (
                ("confidence", payload.confidence),
                ("started_at", payload.started_at),
                ("ended_at", payload.ended_at),
                ("note", payload.note),
            )
            if value is not None
        }
        if not stated:  # an edit that cleared every column: cite the evidence, change nothing
            self._assert(TargetKind.EDGE, edge_id, None, None, payload)
            return
        self.conn.execute(
            sa.update(schema.edge).where(schema.edge.c.id == edge_id).values(**stated)
        )
        for name, value in stated.items():
            self._assert(TargetKind.EDGE, edge_id, name, _json(value), payload)

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
