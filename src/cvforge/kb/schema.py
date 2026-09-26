"""Table definitions for the knowledge base (ADR-0001, ADR-0006).

SQLAlchemy Core `Table` objects only: no ORM, no declarative models. This module
declares shape; it never reads or writes. Reads live in `kb/queries.py`, and every
write lives in `kb/apply.py`.

The schema is expected to be reshaped several times, so two things here exist
for the benefit of future migrations rather than for today:

- `NAMING_CONVENTION` gives every constraint a deterministic name. SQLite cannot
  `ALTER` a constraint in place, so Alembic's batch mode rebuilds the table and
  must be able to refer to each constraint by name.
- Closed vocabularies are CHECK constraints built from `kb/vocab.py`. Widening a
  vocabulary therefore produces a visible migration, not a silent behaviour change.
"""

import sqlalchemy as sa

from cvforge.kb.vocab import (
    CREDENTIAL_TYPES,
    ORG_TYPES,
    SKILL_CATEGORIES,
    Classification,
    EntityKind,
    KnowledgeState,
    OpStatus,
    OpType,
    Origin,
    ProposalStatus,
    Rel,
    SourceKind,
    TargetKind,
    values,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _in(column: str, allowed: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{value}'" for value in allowed)
    return sa.CheckConstraint(f"{column} IN ({quoted})", name=name)


def _nullable_in(column: str, allowed: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{value}'" for value in allowed)
    return sa.CheckConstraint(f"{column} IS NULL OR {column} IN ({quoted})", name=name)


def _dates_ordered(name: str = "dates_ordered") -> sa.CheckConstraint:
    return sa.CheckConstraint(
        "started_at IS NULL OR ended_at IS NULL OR ended_at >= started_at", name=name
    )


def _child_id() -> sa.Column[int]:
    return sa.Column(
        "id", sa.Integer, sa.ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )


# --- entities (joined-table inheritance: one id space) -----------------------

entity = sa.Table(
    "entity",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("normalized_name", sa.String, nullable=False, index=True),
    sa.Column("summary", sa.String),
    sa.Column("state", sa.String, nullable=False),
    sa.Column("first_seen_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
    _in("kind", values(EntityKind), "kind"),
    _in("state", values(KnowledgeState), "state"),
    sa.CheckConstraint("length(name) > 0", name="name_not_empty"),
)

skill = sa.Table(
    "skill",
    metadata,
    _child_id(),
    sa.Column("category", sa.String),
    _nullable_in("category", SKILL_CATEGORIES, "category"),
)

project = sa.Table(
    "project",
    metadata,
    _child_id(),
    sa.Column("started_at", sa.Date),
    sa.Column("ended_at", sa.Date),
    sa.Column("context", sa.String),
    _dates_ordered(),
)

organization = sa.Table(
    "organization",
    metadata,
    _child_id(),
    sa.Column("org_type", sa.String),
    sa.Column("industry", sa.String),
    sa.Column("size", sa.String),
    _nullable_in("org_type", ORG_TYPES, "org_type"),
)

role = sa.Table(
    "role",
    metadata,
    _child_id(),
    sa.Column("title", sa.String),
    sa.Column("seniority", sa.String),
    sa.Column("started_at", sa.Date),
    sa.Column("ended_at", sa.Date),
    sa.Column("employment_type", sa.String),
    _dates_ordered(),
)

education = sa.Table(
    "education",
    metadata,
    _child_id(),
    sa.Column("degree", sa.String),
    sa.Column("field", sa.String),
    sa.Column("started_at", sa.Date),
    sa.Column("ended_at", sa.Date),
    sa.Column("grade", sa.String),
    _dates_ordered(),
)

# No `issuer` column: spec §4.1 prose makes the issuing organization an
# `at_organization` edge, and a text copy of it would be a second place to look.
credential = sa.Table(
    "credential",
    metadata,
    _child_id(),
    sa.Column("credential_type", sa.String),
    sa.Column("issued_at", sa.Date),
    sa.Column("expires_at", sa.Date),
    sa.Column("credential_id", sa.String),
    sa.Column("url", sa.String),
    _nullable_in("credential_type", CREDENTIAL_TYPES, "credential_type"),
    sa.CheckConstraint(
        "issued_at IS NULL OR expires_at IS NULL OR expires_at >= issued_at",
        name="dates_ordered",
    ),
)

achievement = sa.Table(
    "achievement",
    metadata,
    _child_id(),
    sa.Column("metric", sa.String),
    sa.Column("value", sa.String),
    sa.Column("occurred_at", sa.Date),
)

responsibility = sa.Table(
    "responsibility",
    metadata,
    _child_id(),
    sa.Column("scope", sa.String),
)

KIND_TABLES: dict[EntityKind, sa.Table] = {
    EntityKind.SKILL: skill,
    EntityKind.PROJECT: project,
    EntityKind.ORGANIZATION: organization,
    EntityKind.ROLE: role,
    EntityKind.EDUCATION: education,
    EntityKind.CREDENTIAL: credential,
    EntityKind.ACHIEVEMENT: achievement,
    EntityKind.RESPONSIBILITY: responsibility,
}

# --- relationships -------------------------------------------------------------

edge = sa.Table(
    "edge",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("src_id", sa.Integer, sa.ForeignKey("entity.id"), nullable=False),
    sa.Column("rel", sa.String, nullable=False),
    sa.Column("dst_id", sa.Integer, sa.ForeignKey("entity.id"), nullable=False),
    sa.Column("confidence", sa.Float),
    sa.Column("started_at", sa.Date),
    sa.Column("ended_at", sa.Date),
    sa.Column("note", sa.String),
    sa.UniqueConstraint("src_id", "rel", "dst_id"),
    _in("rel", values(Rel), "rel"),
    _dates_ordered(),
    sa.CheckConstraint("src_id != dst_id", name="no_self_loop"),
    sa.CheckConstraint(
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
    ),
)

# --- provenance -----------------------------------------------------------------

source = sa.Table(
    "source",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("label", sa.String, nullable=False),
    sa.Column("uri", sa.String),
    sa.Column("content_hash", sa.String),
    sa.Column("captured_at", sa.DateTime, nullable=False),
    sa.Column("raw_text_path", sa.String),
    _in("kind", values(SourceKind), "kind"),
)

evidence = sa.Table(
    "evidence",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("source_id", sa.Integer, sa.ForeignKey("source.id"), nullable=False),
    sa.Column("locator", sa.String, nullable=False),
    sa.Column("excerpt", sa.String, nullable=False),
)

# `target_id` is polymorphic (entity or edge), so it cannot carry a foreign key.
# `queries.orphans()` and tests/integration/test_invariants.py cover it instead.
assertion = sa.Table(
    "assertion",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("target_kind", sa.String, nullable=False),
    sa.Column("target_id", sa.Integer, nullable=False),
    sa.Column("field", sa.String),
    sa.Column("value_json", sa.JSON),
    sa.Column("evidence_id", sa.Integer, sa.ForeignKey("evidence.id"), nullable=False),
    sa.Column("confidence", sa.Float),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Index("ix_assertion_target", "target_kind", "target_id"),
    _in("target_kind", values(TargetKind), "target_kind"),
)

# --- review pipeline -------------------------------------------------------------

proposal = sa.Table(
    "proposal",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("origin", sa.String, nullable=False),
    sa.Column("source_id", sa.Integer, sa.ForeignKey("source.id"), nullable=False),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("summary", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("applied_at", sa.DateTime),
    _in("origin", values(Origin), "origin"),
    _in("status", values(ProposalStatus), "status"),
)

# The classification target is (target_kind, target_id) rather than the spec's
# `target_entity_id` + `conflict_with_id`: FR-08 requires naming an entity OR an
# edge, and one polymorphic pair says that in one place (ADR-0009).
operation = sa.Table(
    "operation",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("proposal_id", sa.Integer, sa.ForeignKey("proposal.id"), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("op_type", sa.String, nullable=False),
    sa.Column("payload_json", sa.JSON, nullable=False),
    sa.Column("classification", sa.String, nullable=False),
    sa.Column("target_kind", sa.String),
    sa.Column("target_id", sa.Integer),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("edited_payload_json", sa.JSON),
    sa.Column("rationale", sa.String),
    sa.UniqueConstraint("proposal_id", "seq"),
    _in("op_type", values(OpType), "op_type"),
    _in("classification", values(Classification), "classification"),
    _in("status", values(OpStatus), "status"),
    _nullable_in("target_kind", values(TargetKind), "target_kind"),
    sa.CheckConstraint(
        "(classification = 'new' AND target_id IS NULL AND target_kind IS NULL)"
        " OR (classification != 'new' AND target_id IS NOT NULL AND target_kind IS NOT NULL)",
        name="target_matches_classification",
    ),
)

commit_log = sa.Table(
    "commit_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("proposal_id", sa.Integer, sa.ForeignKey("proposal.id"), nullable=False),
    sa.Column("applied_at", sa.DateTime, nullable=False),
    sa.Column("operation_ids_json", sa.JSON, nullable=False),
)
