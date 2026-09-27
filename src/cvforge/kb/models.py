"""Typed boundary models for the knowledge base: operation payloads and proposals.

Everything an agent (or a reviewer's edit) hands to the write path passes through
these models first, so a malformed operation is rejected here, before it can be
stored for review, let alone committed. They are plain data: nothing in this
module touches the database.
"""

import re
from datetime import date
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from cvforge.kb.vocab import (
    Classification,
    EntityKind,
    KnowledgeState,
    OpType,
    Origin,
    Rel,
    TargetKind,
)

_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Derive the deterministic lookup key for an entity name (FR-01).

    Case-folded and whitespace-collapsed, nothing more: "PostgreSQL" and
    "postgres" stay different keys. Recognising those as the same thing is
    similarity search's job (`duplicate`, ADR-0009), not normalization's.

    Args:
        name: The display name.

    Returns:
        The normalized name.
    """
    return _WHITESPACE.sub(" ", name).strip().casefold()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_dates(start: date | None, end: date | None, what: str) -> None:
    if start is not None and end is not None and end < start:
        raise ValueError(f"{what}: end {end} is earlier than start {start}")


# --- kind-specific attributes (spec §4.1) --------------------------------------


class SkillAttributes(_Strict):
    """Attributes of a `skill`."""

    category: Literal["language", "framework", "tool", "platform", "method", "soft"] | None = None


class ProjectAttributes(_Strict):
    """Attributes of a `project`."""

    started_at: date | None = None
    ended_at: date | None = None
    context: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        _check_dates(self.started_at, self.ended_at, "project")
        return self


class OrganizationAttributes(_Strict):
    """Attributes of an `organization`."""

    org_type: Literal["employer", "client", "institution"] | None = None
    industry: str | None = None
    size: str | None = None


class RoleAttributes(_Strict):
    """Attributes of a `role`."""

    title: str | None = None
    seniority: str | None = None
    started_at: date | None = None
    ended_at: date | None = None
    employment_type: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        _check_dates(self.started_at, self.ended_at, "role")
        return self


class EducationAttributes(_Strict):
    """Attributes of an `education` entry."""

    degree: str | None = None
    field: str | None = None
    started_at: date | None = None
    ended_at: date | None = None
    grade: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        _check_dates(self.started_at, self.ended_at, "education")
        return self


class CredentialAttributes(_Strict):
    """Attributes of a `credential`. The issuer is an `at_organization` edge."""

    credential_type: Literal["certification", "course", "bootcamp"] | None = None
    issued_at: date | None = None
    expires_at: date | None = None
    credential_id: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        _check_dates(self.issued_at, self.expires_at, "credential")
        return self


class AchievementAttributes(_Strict):
    """Attributes of an `achievement`."""

    metric: str | None = None
    value: str | None = None
    occurred_at: date | None = None


class ResponsibilityAttributes(_Strict):
    """Attributes of a `responsibility`."""

    scope: str | None = None


KIND_ATTRIBUTES: dict[EntityKind, type[_Strict]] = {
    EntityKind.SKILL: SkillAttributes,
    EntityKind.PROJECT: ProjectAttributes,
    EntityKind.ORGANIZATION: OrganizationAttributes,
    EntityKind.ROLE: RoleAttributes,
    EntityKind.EDUCATION: EducationAttributes,
    EntityKind.CREDENTIAL: CredentialAttributes,
    EntityKind.ACHIEVEMENT: AchievementAttributes,
    EntityKind.RESPONSIBILITY: ResponsibilityAttributes,
}

# Fields on the base `entity` row that an `update_field` may change. `state` is
# absent on purpose: it changes only through `set_state` (FR-04).
COMMON_FIELDS = frozenset({"name", "summary"})


# --- references and payloads --------------------------------------------------


class OpRef(_Strict):
    """A reference to an entity created by an earlier operation in the same proposal."""

    op: int = Field(ge=0, description="The `seq` of the `create_entity` operation.")


EntityRef = int | OpRef
"""An existing entity id, or an entity created earlier in the same proposal."""


class CreateEntity(_Strict):
    """Create a new entity of `kind`, evidenced by `evidence_id`."""

    op_type: Literal[OpType.CREATE_ENTITY] = OpType.CREATE_ENTITY
    kind: EntityKind
    name: str = Field(min_length=1)
    summary: str | None = None
    state: KnowledgeState = KnowledgeState.CONFIRMED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_id: int

    @model_validator(mode="after")
    def _attributes_fit_kind(self) -> Self:
        if not normalize_name(self.name):
            raise ValueError("name must contain a non-whitespace character")
        KIND_ATTRIBUTES[self.kind].model_validate(self.attributes)
        return self

    def typed_attributes(self) -> dict[str, Any]:
        """Return the attributes parsed and typed for this kind, unset values dropped.

        Returns:
            Column name to Python value, ready for the kind's child table.
        """
        model = KIND_ATTRIBUTES[self.kind].model_validate(self.attributes)
        return model.model_dump(exclude_none=True)


class UpdateField(_Strict):
    """Change one field of an existing entity to `value`."""

    op_type: Literal[OpType.UPDATE_FIELD] = OpType.UPDATE_FIELD
    entity_id: int
    field: str = Field(min_length=1)
    value: JsonValue
    evidence_id: int

    @model_validator(mode="after")
    def _not_state(self) -> Self:
        if self.field == "state":
            raise ValueError("state changes only through a set_state operation (FR-04)")
        return self


class AddEdge(_Strict):
    """Relate two entities with a closed-vocabulary `rel`."""

    op_type: Literal[OpType.ADD_EDGE] = OpType.ADD_EDGE
    src: EntityRef
    rel: Rel
    dst: EntityRef
    confidence: float | None = Field(default=None, ge=0, le=1)
    started_at: date | None = None
    ended_at: date | None = None
    note: str | None = None
    evidence_id: int

    @model_validator(mode="after")
    def _valid(self) -> Self:
        _check_dates(self.started_at, self.ended_at, "edge")
        if self.src == self.dst:
            raise ValueError("an edge cannot relate an entity to itself")
        return self


class AttachEvidence(_Strict):
    """Add supporting evidence to an existing entity, edge or field."""

    op_type: Literal[OpType.ATTACH_EVIDENCE] = OpType.ATTACH_EVIDENCE
    target_kind: TargetKind
    target_id: int
    field: str | None = None
    evidence_id: int


class MergeDuplicate(_Strict):
    """Fold `merge_id` into `keep_id`. Applied from M1b, with similarity search."""

    op_type: Literal[OpType.MERGE_DUPLICATE] = OpType.MERGE_DUPLICATE
    keep_id: int
    merge_id: int
    evidence_id: int

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if self.keep_id == self.merge_id:
            raise ValueError("cannot merge an entity into itself")
        return self


class SetState(_Strict):
    """Change an entity's knowledge state (the only way to do so, FR-04)."""

    op_type: Literal[OpType.SET_STATE] = OpType.SET_STATE
    entity: EntityRef
    state: KnowledgeState
    evidence_id: int


Payload = Annotated[
    CreateEntity | UpdateField | AddEdge | AttachEvidence | MergeDuplicate | SetState,
    Field(discriminator="op_type"),
]


class OperationDraft(_Strict):
    """One proposed operation, classified, as submitted for review."""

    seq: int = Field(ge=0)
    payload: Payload
    classification: Classification
    target_kind: TargetKind | None = None
    target_id: int | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _target_matches_classification(self) -> Self:
        named = self.target_kind is not None and self.target_id is not None
        partial = (self.target_kind is None) != (self.target_id is None)
        if partial:
            raise ValueError("target_kind and target_id are set together or not at all")
        if self.classification is Classification.NEW and named:
            raise ValueError("a `new` operation names no target (FR-08)")
        if self.classification is not Classification.NEW and not named:
            raise ValueError(f"a `{self.classification}` operation must name its target (FR-08)")
        return self


class ProposalDraft(_Strict):
    """A proposal as produced by an intake: ordered, classified operations."""

    origin: Origin
    source_id: int
    summary: str
    operations: list[OperationDraft]

    @model_validator(mode="after")
    def _references_resolve(self) -> Self:
        seqs = [op.seq for op in self.operations]
        if len(seqs) != len(set(seqs)):
            raise ValueError("operation seq values must be unique within a proposal")
        creates = {op.seq for op in self.operations if isinstance(op.payload, CreateEntity)}
        for op in self.operations:
            for ref in _op_refs(op.payload):
                if ref.op not in creates or ref.op >= op.seq:
                    raise ValueError(
                        f"operation {op.seq} refers to op {ref.op}, which is not an earlier "
                        "create_entity in this proposal"
                    )
        return self


def _op_refs(payload: BaseModel) -> list[OpRef]:
    refs: list[OpRef] = []
    if isinstance(payload, AddEdge):
        refs = [r for r in (payload.src, payload.dst) if isinstance(r, OpRef)]
    elif isinstance(payload, SetState) and isinstance(payload.entity, OpRef):
        refs = [payload.entity]
    return refs


def parse_payload(
    data: object,
) -> CreateEntity | UpdateField | AddEdge | AttachEvidence | MergeDuplicate | SetState:
    """Validate a raw payload (e.g. a reviewer's edit) into its typed model.

    Args:
        data: A JSON-shaped payload carrying an `op_type` discriminator.

    Returns:
        The typed payload.

    Raises:
        pydantic.ValidationError: If the payload does not fit any operation type.
    """
    return _PayloadBox.model_validate({"payload": data}).payload


class _PayloadBox(_Strict):
    payload: Payload
