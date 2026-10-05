"""`CommitResult.reindex_ids`: the existing entities whose embedded text just changed."""

from collections.abc import Callable

import pytest
import sqlalchemy as sa

from cvforge.kb import apply

Propose = Callable[..., int]


@pytest.fixture
def role(kb: sa.Engine, propose: Propose) -> int:
    created = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "role", "name": "Engineer"}, accept=True)
    )
    return created.entity_ids[0]


def _update(role: int, field: str, value: object) -> dict[str, object]:
    return {"op_type": "update_field", "entity_id": role, "field": field, "value": value}


@pytest.mark.parametrize(("field", "value"), [("name", "Staff Engineer"), ("summary", "builds")])
def test_a_changed_name_or_summary_is_listed(
    kb: sa.Engine, propose: Propose, role: int, field: str, value: str
) -> None:
    result = apply.commit_proposal(kb, propose(_update(role, field, value), accept=True))
    assert result.reindex_ids == [role]


def test_a_field_the_index_does_not_embed_is_not_listed(
    kb: sa.Engine, propose: Propose, role: int
) -> None:
    result = apply.commit_proposal(kb, propose(_update(role, "title", "Lead"), accept=True))
    assert result.reindex_ids == []


def test_a_restated_name_changes_nothing_so_is_not_listed(
    kb: sa.Engine, propose: Propose, role: int
) -> None:
    result = apply.commit_proposal(kb, propose(_update(role, "name", "engineer"), accept=True))
    assert result.reindex_ids == []  # classified `known`: it only adds evidence


def test_creating_an_entity_lists_nothing_extra(kb: sa.Engine, propose: Propose) -> None:
    result = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True)
    )
    assert result.reindex_ids == []  # new entities are already in `entity_ids`
