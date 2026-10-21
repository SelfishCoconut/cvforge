"""A document result converts with one evidence span per item, and drops what has none (FR-15)."""

from cvforge.kb.models import AddEdge, CreateEntity
from cvforge.kb.vocab import EntityKind, Rel
from cvforge.llm.convert import to_payloads
from cvforge.llm.schemas import (
    DocumentEdge,
    DocumentFact,
    DocumentResult,
    ExtractedEdge,
    ExtractedFact,
    IngestResult,
)

RUST = DocumentFact(local_id="s", kind=EntityKind.SKILL, name="Rust", excerpt="I use Rust")
PARSER = DocumentFact(
    local_id="e", kind=EntityKind.PROJECT, name="Log parser", excerpt="built a log parser"
)
USED = DocumentEdge(src="s", rel=Rel.USED_IN, dst="e", excerpt="Rust in the parser")


def test_each_item_is_bound_to_its_own_evidence() -> None:
    ids = {"I use Rust": 10, "built a log parser": 11, "Rust in the parser": 12}

    converted = to_payloads(
        DocumentResult(facts=[RUST, PARSER], edges=[USED]),
        evidence_id=lambda item: ids[item.excerpt],  # type: ignore[union-attr]
    )

    assert [p.evidence_id for p in converted.payloads] == [10, 11, 12]
    assert isinstance(converted.payloads[0], CreateEntity)
    assert isinstance(converted.payloads[2], AddEdge)
    assert converted.rejected == []


def test_a_fact_with_no_resolvable_locator_is_dropped_with_its_edges() -> None:
    converted = to_payloads(
        DocumentResult(facts=[RUST, PARSER], edges=[USED]),
        evidence_id=lambda item: None if item is PARSER else 10,
    )

    assert [p.evidence_id for p in converted.payloads] == [10]
    reasons = {r.item: r.reason for r in converted.rejected}
    assert reasons["fact 'e'"] == "no resolvable locator"
    assert "rejected fact 'e'" in reasons["edge s -[used_in]-> e"]


def test_an_edge_with_no_resolvable_locator_is_dropped_alone() -> None:
    converted = to_payloads(
        DocumentResult(facts=[RUST, PARSER], edges=[USED]),
        evidence_id=lambda item: None if item is USED else 10,
    )

    assert len(converted.payloads) == 2
    assert [r.reason for r in converted.rejected] == ["no resolvable locator"]


def test_a_single_evidence_id_still_binds_every_item_for_chat() -> None:
    result = IngestResult(
        reply="ok",
        facts=[ExtractedFact(local_id="s", kind=EntityKind.SKILL, name="Rust")],
        edges=[ExtractedEdge(src="s", rel=Rel.USED_IN, dst=5)],
    )

    converted = to_payloads(result, evidence_id=7)

    assert [p.evidence_id for p in converted.payloads] == [7, 7]
