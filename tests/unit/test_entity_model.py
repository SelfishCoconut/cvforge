"""FR-01 (entities) and FR-04 (knowledge state)."""

from collections.abc import Callable
from datetime import date

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from cvforge.kb import apply, queries, schema
from cvforge.kb.models import CreateEntity, UpdateField, normalize_name
from cvforge.kb.vocab import EntityKind, KnowledgeState, TargetKind

ONE_OF_EACH: dict[EntityKind, dict[str, object]] = {
    EntityKind.SKILL: {"category": "language"},
    EntityKind.PROJECT: {
        "started_at": "2021-01-01",
        "ended_at": "2022-06-30",
        "context": "internal",
    },
    EntityKind.ORGANIZATION: {"org_type": "employer", "industry": "logistics", "size": "200"},
    EntityKind.ROLE: {"title": "Backend engineer", "seniority": "mid", "started_at": "2021-01-01"},
    EntityKind.EDUCATION: {"degree": "BSc", "field": "Computer Science", "grade": "8.1"},
    EntityKind.CREDENTIAL: {"credential_type": "certification", "issued_at": "2023-03-01"},
    EntityKind.ACHIEVEMENT: {"metric": "p95 latency", "value": "-40%", "occurred_at": "2022-05-01"},
    EntityKind.RESPONSIBILITY: {"scope": "on-call rotation"},
}

Propose = Callable[..., int]


@pytest.mark.parametrize("kind", list(EntityKind))
def test_each_kind_round_trips_with_every_field(
    kb: sa.Engine, propose: Propose, kind: EntityKind
) -> None:
    create = {
        "op_type": "create_entity",
        "kind": kind.value,
        "name": f"Synthetic {kind.value}",
        "summary": "a synthetic fixture",
        "attributes": ONE_OF_EACH[kind],
    }
    result = apply.commit_proposal(kb, propose(create, accept=True))
    with kb.connect() as conn:
        stored = queries.get_entity(conn, result.entity_ids[0])
    assert stored is not None
    assert (stored.kind, stored.name, stored.summary, stored.state) == (
        kind,
        f"Synthetic {kind.value}",
        "a synthetic fixture",
        KnowledgeState.CONFIRMED,
    )
    assert stored.normalized_name == f"synthetic {kind.value}"
    expected = CreateEntity.model_validate({**create, "evidence_id": 1}).typed_attributes()
    assert {k: v for k, v in stored.attributes.items() if v is not None} == expected


def test_unknown_kind_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        CreateEntity.model_validate({"kind": "hobby", "name": "x", "evidence_id": 1})


def test_unknown_kind_is_rejected_by_the_database_too(kb: sa.Engine) -> None:
    """A value that slips past Pydantic still cannot reach a row (CHECK constraint)."""
    now = sa.func.current_timestamp()
    with pytest.raises(sa.exc.IntegrityError, match="ck_entity_kind"), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.entity).values(
                kind="hobby",
                name="x",
                normalized_name="x",
                state="confirmed",
                first_seen_at=now,
                updated_at=now,
            )
        )


def test_attributes_of_another_kind_are_rejected() -> None:
    with pytest.raises(ValidationError, match="degree"):
        CreateEntity.model_validate(
            {"kind": "skill", "name": "Rust", "attributes": {"degree": "BSc"}, "evidence_id": 1}
        )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("  Rust ", "rust"),
        ("Machine   Learning", "machine learning"),
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),
    ],
)
def test_normalized_name_is_casefolded_and_whitespace_collapsed(raw: str, normalized: str) -> None:
    assert normalize_name(raw) == normalized


def test_normalized_name_is_queryable(kb: sa.Engine, propose: Propose) -> None:
    apply.commit_proposal(
        kb,
        propose({"op_type": "create_entity", "kind": "skill", "name": "Type  Script"}, accept=True),
    )
    with kb.connect() as conn:
        assert len(queries.find_by_name(conn, EntityKind.SKILL, "type script")) == 1
        assert queries.find_by_name(conn, EntityKind.PROJECT, "type script") == []


def test_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateEntity.model_validate({"kind": "skill", "name": "   ", "evidence_id": 1})


def test_inverted_dates_are_rejected() -> None:
    with pytest.raises(ValidationError, match="earlier"):
        CreateEntity.model_validate(
            {
                "kind": "role",
                "name": "Engineer",
                "attributes": {"started_at": "2022-01-01", "ended_at": "2021-01-01"},
                "evidence_id": 1,
            }
        )


# --- FR-04: knowledge state -----------------------------------------------------


@pytest.mark.parametrize("state", list(KnowledgeState))
def test_each_state_round_trips_and_filters(
    kb: sa.Engine, propose: Propose, state: KnowledgeState
) -> None:
    apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Go", "state": state.value},
            {
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Zig",
                "state": "gap" if state != KnowledgeState.GAP else "learning",
            },
            accept=True,
        ),
    )
    with kb.connect() as conn:
        matching = queries.list_entities(conn, state=state)
    assert [e.name for e in matching] == ["Go"]


def test_state_outside_the_closed_set_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateEntity.model_validate(
            {"kind": "skill", "name": "Go", "state": "rusty", "evidence_id": 1}
        )


def test_state_cannot_change_through_update_field() -> None:
    with pytest.raises(ValidationError, match="set_state"):
        UpdateField.model_validate(
            {"entity_id": 1, "field": "state", "value": "gap", "evidence_id": 1}
        )


def test_set_state_changes_state_and_asserts_it(kb: sa.Engine, propose: Propose) -> None:
    created = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": "Go"}, accept=True)
    )
    entity_id = created.entity_ids[0]
    apply.commit_proposal(
        kb, propose({"op_type": "set_state", "entity": entity_id, "state": "archived"}, accept=True)
    )
    with kb.connect() as conn:
        stored = queries.get_entity(conn, entity_id)
        history = [
            p.value
            for p in queries.provenance(conn, TargetKind.ENTITY, entity_id)
            if p.field == "state"
        ]
    assert stored is not None and stored.state is KnowledgeState.ARCHIVED
    assert history == ["confirmed", "archived"]


def test_role_dates_are_typed(kb: sa.Engine, propose: Propose) -> None:
    result = apply.commit_proposal(
        kb,
        propose(
            {
                "op_type": "create_entity",
                "kind": "role",
                "name": "Engineer",
                "attributes": {"started_at": "2020-02-01"},
            },
            accept=True,
        ),
    )
    with kb.connect() as conn:
        stored = queries.get_entity(conn, result.entity_ids[0])
    assert stored is not None and stored.attributes["started_at"] == date(2020, 2, 1)


def test_undocumented_is_not_a_knowledge_state() -> None:
    """FR-04 c4: 'something never recorded' is a match verdict (§4.4), never a state."""
    assert {s.value for s in KnowledgeState} == {"confirmed", "learning", "gap", "archived"}
