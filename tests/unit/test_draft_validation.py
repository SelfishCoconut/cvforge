"""Validation and classification branches that no test reached (audit finding 6).

A draft that does not hold together is refused before review, and an operation
type with no stored counterpart is `new`. Each refusal is matched on its message,
so a different validation error cannot satisfy the test by accident.
"""

from collections.abc import Mapping

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from cvforge.kb.classify import NEW, Verdict, classify
from cvforge.kb.models import OperationDraft, ProposalDraft, parse_payload

SKILL = {"op_type": "create_entity", "kind": "skill", "name": "Rust"}


def _draft(*operations: dict[str, object]) -> dict[str, object]:
    return {"origin": "chat", "source_id": 1, "summary": "s", "operations": list(operations)}


def _op(seq: int, payload: Mapping[str, object], **extra: object) -> dict[str, object]:
    return {
        "seq": seq,
        "payload": {"evidence_id": 1, **payload},
        "classification": "new",
        **extra,
    }


def test_two_operations_cannot_share_a_seq() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ProposalDraft.model_validate(_draft(_op(0, SKILL), _op(0, SKILL)))


def test_an_edge_may_only_refer_to_an_earlier_create() -> None:
    forward = {"op_type": "add_edge", "src": {"op": 1}, "rel": "used_in", "dst": 5}
    with pytest.raises(ValidationError, match="not an earlier create_entity"):
        ProposalDraft.model_validate(_draft(_op(0, forward), _op(1, SKILL)))


def test_a_reference_to_an_operation_that_does_not_exist_is_refused() -> None:
    dangling = {"op_type": "add_edge", "src": {"op": 7}, "rel": "used_in", "dst": 5}
    with pytest.raises(ValidationError, match="not an earlier create_entity"):
        ProposalDraft.model_validate(_draft(_op(0, dangling)))


def test_set_state_may_refer_to_an_earlier_create_but_not_a_later_one() -> None:
    later = {"op_type": "set_state", "entity": {"op": 1}, "state": "gap"}
    with pytest.raises(ValidationError, match="not an earlier create_entity"):
        ProposalDraft.model_validate(_draft(_op(0, later), _op(1, SKILL)))
    earlier = {"op_type": "set_state", "entity": {"op": 0}, "state": "gap"}
    ProposalDraft.model_validate(_draft(_op(0, SKILL), _op(1, earlier)))  # holds together


def test_a_target_is_named_completely_or_not_at_all() -> None:
    with pytest.raises(ValidationError, match="together or not at all"):
        OperationDraft.model_validate(
            {
                "seq": 0,
                "payload": {"evidence_id": 1, **SKILL},
                "classification": "known",
                "target_kind": "entity",
            }
        )


def test_an_entity_cannot_be_merged_into_itself() -> None:
    with pytest.raises(ValidationError, match="itself"):
        parse_payload({"evidence_id": 1, "op_type": "merge_duplicate", "keep_id": 3, "merge_id": 3})


@pytest.mark.parametrize(
    "payload",
    [
        {"op_type": "update_field", "entity_id": 99, "field": "summary", "value": "x"},
        {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": 3},
        {"op_type": "add_edge", "src": 3, "rel": "used_in", "dst": {"op": 0}},
        {"op_type": "set_state", "entity": {"op": 0}, "state": "gap"},
        {"op_type": "set_state", "entity": 99, "state": "gap"},
        {"op_type": "attach_evidence", "target_kind": "entity", "target_id": 1},
    ],
    ids=[
        "update of an entity that is not stored",
        "edge whose source does not exist yet",
        "edge whose destination does not exist yet",
        "state of an entity that does not exist yet",
        "state of an entity that is not stored",
        "attach_evidence has no stored counterpart",
    ],
)
def test_an_operation_with_no_stored_counterpart_is_new(
    kb: sa.Engine, payload: dict[str, object]
) -> None:
    with kb.connect() as conn:
        verdict: Verdict = classify(conn, parse_payload({"evidence_id": 1, **payload}))
    assert verdict == NEW


def test_a_similarity_finder_that_finds_nothing_leaves_a_create_new(kb: sa.Engine) -> None:
    with kb.connect() as conn:
        verdict = classify(
            conn, parse_payload({"evidence_id": 1, **SKILL}), similar=lambda _k, _n: None
        )
    assert verdict == NEW
