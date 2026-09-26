"""FR-08: every operation is classified new / known / duplicate / conflict (ADR-0009)."""

from collections.abc import Callable

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from cvforge.kb import apply, queries
from cvforge.kb.classify import Verdict, classify
from cvforge.kb.models import OperationDraft, parse_payload
from cvforge.kb.vocab import Classification, EntityKind, TargetKind

Propose = Callable[..., int]


def _verdict(kb: sa.Engine, payload: dict[str, object], **kwargs: object) -> Verdict:
    with kb.connect() as conn:
        return classify(conn, parse_payload({"evidence_id": 1, **payload}), **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def stored(kb: sa.Engine, propose: Propose) -> dict[str, int]:
    """A small stored graph: Rust (skill), Parser (project), Rust used_in Parser."""
    result = apply.commit_proposal(
        kb,
        propose(
            {"op_type": "create_entity", "kind": "skill", "name": "Rust", "summary": "systems"},
            {
                "op_type": "create_entity",
                "kind": "project",
                "name": "Parser",
                "attributes": {"started_at": "2021-01-01"},
            },
            {
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "used_in",
                "dst": {"op": 1},
                "started_at": "2021-01-01",
            },
            accept=True,
        ),
    )
    with kb.connect() as conn:
        edge = queries.find_edge(conn, result.entity_ids[0], "used_in", result.entity_ids[1])
    assert edge is not None
    return {"rust": result.entity_ids[0], "parser": result.entity_ids[1], "edge": edge.id}


def test_a_genuinely_new_fact_is_new_with_no_target(kb: sa.Engine, stored: dict[str, int]) -> None:
    verdict = _verdict(kb, {"op_type": "create_entity", "kind": "skill", "name": "Haskell"})
    assert verdict == Verdict(Classification.NEW)


def test_restating_an_entity_is_known_and_names_it(kb: sa.Engine, stored: dict[str, int]) -> None:
    verdict = _verdict(kb, {"op_type": "create_entity", "kind": "skill", "name": "  rust "})
    assert verdict == Verdict(Classification.KNOWN, TargetKind.ENTITY, stored["rust"])


def test_a_role_name_match_is_not_known(kb: sa.Engine, propose: Propose) -> None:
    """Two roles with the same title are routinely different facts (ADR-0009)."""
    apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "role", "name": "Engineer"}, accept=True)
    )
    verdict = _verdict(kb, {"op_type": "create_entity", "kind": "role", "name": "Engineer"})
    assert verdict.classification is Classification.NEW


def test_a_similar_but_differently_named_entity_is_a_duplicate(
    kb: sa.Engine, stored: dict[str, int]
) -> None:
    def similar(kind: EntityKind, name: str) -> int | None:
        return stored["rust"] if (kind, name) == (EntityKind.SKILL, "Rust-lang") else None

    verdict = _verdict(
        kb, {"op_type": "create_entity", "kind": "skill", "name": "Rust-lang"}, similar=similar
    )
    assert verdict == Verdict(Classification.DUPLICATE, TargetKind.ENTITY, stored["rust"])


def test_restating_a_field_is_known_and_contradicting_it_is_a_conflict(
    kb: sa.Engine, stored: dict[str, int]
) -> None:
    same = _verdict(
        kb,
        {
            "op_type": "update_field",
            "entity_id": stored["rust"],
            "field": "summary",
            "value": "Systems",
        },
    )
    other = _verdict(
        kb,
        {
            "op_type": "update_field",
            "entity_id": stored["rust"],
            "field": "summary",
            "value": "web",
        },
    )
    empty = _verdict(
        kb,
        {
            "op_type": "update_field",
            "entity_id": stored["parser"],
            "field": "context",
            "value": "x",
        },
    )
    assert same == Verdict(Classification.KNOWN, TargetKind.ENTITY, stored["rust"])
    assert other == Verdict(Classification.CONFLICT, TargetKind.ENTITY, stored["rust"])
    assert empty.classification is Classification.NEW


def test_a_kind_attribute_conflict_names_the_entity(kb: sa.Engine, stored: dict[str, int]) -> None:
    verdict = _verdict(
        kb,
        {
            "op_type": "update_field",
            "entity_id": stored["parser"],
            "field": "started_at",
            "value": "2020-05-01",
        },
    )
    assert verdict == Verdict(Classification.CONFLICT, TargetKind.ENTITY, stored["parser"])


def test_edges_are_known_or_conflicting_by_their_dates(
    kb: sa.Engine, stored: dict[str, int]
) -> None:
    base = {"op_type": "add_edge", "src": stored["rust"], "rel": "used_in", "dst": stored["parser"]}
    assert _verdict(kb, base) == Verdict(Classification.KNOWN, TargetKind.EDGE, stored["edge"])
    moved = _verdict(kb, {**base, "started_at": "2019-01-01"})
    assert moved == Verdict(Classification.CONFLICT, TargetKind.EDGE, stored["edge"])
    assert _verdict(kb, {**base, "rel": "demonstrates"}).classification is Classification.NEW


def test_state_restated_is_known_and_changed_is_new(kb: sa.Engine, stored: dict[str, int]) -> None:
    same = _verdict(kb, {"op_type": "set_state", "entity": stored["rust"], "state": "confirmed"})
    change = _verdict(kb, {"op_type": "set_state", "entity": stored["rust"], "state": "archived"})
    assert same == Verdict(Classification.KNOWN, TargetKind.ENTITY, stored["rust"])
    assert change.classification is Classification.NEW


@pytest.mark.parametrize("classification", ["known", "duplicate", "conflict"])
def test_a_non_new_classification_without_a_target_is_rejected(classification: str) -> None:
    with pytest.raises(ValidationError, match="must name its target"):
        OperationDraft.model_validate(
            {
                "seq": 0,
                "payload": {
                    "op_type": "create_entity",
                    "kind": "skill",
                    "name": "Go",
                    "evidence_id": 1,
                },
                "classification": classification,
            }
        )


def test_a_new_operation_naming_a_target_is_rejected() -> None:
    with pytest.raises(ValidationError, match="names no target"):
        OperationDraft.model_validate(
            {
                "seq": 0,
                "payload": {
                    "op_type": "create_entity",
                    "kind": "skill",
                    "name": "Go",
                    "evidence_id": 1,
                },
                "classification": "new",
                "target_kind": "entity",
                "target_id": 3,
            }
        )


# --- what accepting each classification does (ADR-0009) -------------------------


def test_accepting_known_adds_evidence_and_creates_nothing(
    kb: sa.Engine, stored: dict[str, int], propose: Propose
) -> None:
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    apply.commit_proposal(
        kb,
        propose(
            (
                {"op_type": "create_entity", "kind": "skill", "name": "rust"},
                "known",
                "entity",
                stored["rust"],
            ),
            {
                "op_type": "add_edge",
                "src": {"op": 0},
                "rel": "demonstrates",
                "dst": stored["parser"],
            },
            accept=True,
        ),
    )
    with kb.connect() as conn:
        after = queries.table_counts(conn)
        edges = queries.neighbours(conn, stored["rust"])
    assert after["entity"] == before["entity"]
    assert (
        after["assertion"] == before["assertion"] + 2
    )  # support for Rust, existence of the new edge
    assert {e.rel for e in edges} == {
        "used_in",
        "demonstrates",
    }  # the op ref resolved to stored Rust


def test_accepting_a_conflict_replaces_the_value_and_keeps_history(
    kb: sa.Engine, stored: dict[str, int], propose: Propose
) -> None:
    update = {
        "op_type": "update_field",
        "entity_id": stored["rust"],
        "field": "summary",
        "value": "web",
    }
    apply.commit_proposal(kb, propose((update, "conflict", "entity", stored["rust"]), accept=True))
    with kb.connect() as conn:
        entity = queries.get_entity(conn, stored["rust"])
        history = [
            p.value
            for p in queries.provenance(conn, TargetKind.ENTITY, stored["rust"])
            if p.field == "summary"
        ]
    assert entity is not None and entity.summary == "web"
    assert history == ["systems", "web"]


def test_accepting_an_edge_conflict_updates_the_stored_edge(
    kb: sa.Engine, stored: dict[str, int], propose: Propose
) -> None:
    edge = {
        "op_type": "add_edge",
        "src": stored["rust"],
        "rel": "used_in",
        "dst": stored["parser"],
        "started_at": "2019-01-01",
    }
    apply.commit_proposal(kb, propose((edge, "conflict", "edge", stored["edge"]), accept=True))
    with kb.connect() as conn:
        updated = queries.find_edge(conn, stored["rust"], "used_in", stored["parser"])
        count = queries.table_counts(conn)["edge"]
    assert updated is not None and str(updated.started_at) == "2019-01-01"
    assert count == 1
