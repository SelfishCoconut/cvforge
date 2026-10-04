"""`llm.convert.to_payloads` turns an agent's facts into typed operations (FR-07)."""

import pytest
from pydantic import ValidationError

from cvforge.kb.models import AddEdge, CreateEntity, OpRef
from cvforge.kb.vocab import EntityKind, Rel
from cvforge.llm.convert import to_payloads
from cvforge.llm.schemas import IngestResult

EVIDENCE = 7


def _fact(
    local_id: str, name: str, kind: EntityKind = EntityKind.SKILL, **extra: object
) -> dict[str, object]:
    return {"local_id": local_id, "kind": kind, "name": name, **extra}


def _result(
    facts: list[dict[str, object]], edges: list[dict[str, object]] | None = None
) -> IngestResult:
    return IngestResult.model_validate({"reply": "ok", "facts": facts, "edges": edges or []})


def test_a_fact_and_an_edge_convert_in_dependency_order() -> None:
    result = _result(
        [_fact("r", "Backend dev", EntityKind.ROLE), _fact("s", "Rust")],
        [{"src": "r", "rel": Rel.USED_IN, "dst": "s", "note": "daily"}],
    )

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert converted.rejected == []
    first, second, edge = converted.payloads
    assert isinstance(first, CreateEntity) and first.kind is EntityKind.ROLE
    assert isinstance(second, CreateEntity) and second.name == "Rust"
    assert isinstance(edge, AddEdge)
    assert (edge.src, edge.dst) == (OpRef(op=0), OpRef(op=1))
    assert edge.note == "daily"
    assert {p.evidence_id for p in converted.payloads} == {EVIDENCE}


def test_an_integer_endpoint_is_an_existing_entity_id() -> None:
    result = _result([_fact("s", "Rust")], [{"src": 42, "rel": Rel.USED_IN, "dst": "s"}])

    edge = to_payloads(result, evidence_id=EVIDENCE).payloads[1]

    assert isinstance(edge, AddEdge) and edge.src == 42 and edge.dst == OpRef(op=0)


def test_a_kind_outside_the_closed_set_fails_at_parse() -> None:
    with pytest.raises(ValidationError):
        _result([_fact("x", "Thing", "hobby")])  # type: ignore[arg-type]


def test_a_rel_outside_the_closed_set_fails_at_parse() -> None:
    with pytest.raises(ValidationError):
        _result([_fact("a", "A"), _fact("b", "B")], [{"src": "a", "rel": "invented", "dst": "b"}])


def test_an_edge_to_an_unknown_local_id_is_rejected_and_the_rest_survives() -> None:
    result = _result([_fact("s", "Rust")], [{"src": "ghost", "rel": Rel.USED_IN, "dst": "s"}])

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert len(converted.payloads) == 1
    assert [r.reason for r in converted.rejected] == ["unknown local id 'ghost'"]


def test_attributes_that_do_not_fit_the_kind_are_rejected() -> None:
    result = _result(
        [
            _fact("s", "Rust", attributes={"category": "not-a-category"}),
            _fact("t", "Go"),
        ]
    )

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert [p.name for p in converted.payloads if isinstance(p, CreateEntity)] == ["Go"]
    assert [r.item for r in converted.rejected] == ["fact 's'"]


def test_an_edge_to_a_rejected_fact_is_rejected_with_the_reason() -> None:
    result = _result(
        [_fact("s", "Rust", attributes={"bogus": 1}), _fact("t", "Go")],
        [{"src": "s", "rel": Rel.USED_IN, "dst": "t"}],
    )

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert len(converted.payloads) == 1
    assert [r.item for r in converted.rejected] == ["fact 's'", "edge s -[used_in]-> t"]


def test_a_duplicate_local_id_is_rejected() -> None:
    result = _result([_fact("s", "Rust"), _fact("s", "Go")])

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert [p.name for p in converted.payloads if isinstance(p, CreateEntity)] == ["Rust"]
    assert [r.reason for r in converted.rejected] == ["duplicate local id 's'"]


def test_an_invalid_edge_is_rejected_not_raised() -> None:
    result = _result([_fact("s", "Rust")], [{"src": "s", "rel": Rel.USED_IN, "dst": "s"}])

    converted = to_payloads(result, evidence_id=EVIDENCE)

    assert len(converted.payloads) == 1
    assert len(converted.rejected) == 1


def test_an_empty_result_converts_to_nothing() -> None:
    converted = to_payloads(IngestResult(reply="thanks"), evidence_id=EVIDENCE)

    assert converted.payloads == [] and converted.rejected == []
