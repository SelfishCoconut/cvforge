"""Pure conversion from an agent's `IngestResult` to typed operation payloads (FR-07).

Nothing the model returns is trusted to be well-formed: a fact or edge that does
not fit is reported in `Converted.rejected` and the rest of the result survives.
"""

from dataclasses import dataclass, field

from pydantic import ValidationError

from cvforge.kb.models import AddEdge, CreateEntity, EntityRef, OpRef, Payload
from cvforge.llm.schemas import ExtractedEdge, ExtractedFact, IngestResult


@dataclass(frozen=True)
class RejectedItem:
    """Something the agent produced that could not become an operation."""

    item: str
    reason: str


@dataclass(frozen=True)
class Converted:
    """Payloads in dependency order, and what was left out and why."""

    payloads: list[Payload] = field(default_factory=list)
    rejected: list[RejectedItem] = field(default_factory=list)


def to_payloads(result: IngestResult, *, evidence_id: int) -> Converted:
    """Convert an agent result into payloads, reporting every item it rejects.

    Facts come first, so an edge's `OpRef` always points at an earlier create.
    A `str` edge endpoint is a fact's local id; an `int` is an existing entity id.

    Args:
        result: The parsed agent output.
        evidence_id: The evidence span every payload is bound to (invariant 3).

    Returns:
        The payloads and the rejected items.
    """
    payloads: list[Payload] = []
    rejected: list[RejectedItem] = []
    refs: dict[str, OpRef] = {}
    dead: set[str] = set()
    for fact in result.facts:
        if fact.local_id in refs or fact.local_id in dead:
            rejected.append(
                RejectedItem(_fact_label(fact), f"duplicate local id {fact.local_id!r}")
            )
            continue
        created = _create(fact, evidence_id, rejected)
        if created is None:
            dead.add(fact.local_id)
            continue
        refs[fact.local_id] = OpRef(op=len(payloads))
        payloads.append(created)
    for edge in result.edges:
        added = _add_edge(edge, evidence_id, refs, dead, rejected)
        if added is not None:
            payloads.append(added)
    return Converted(payloads, rejected)


def _fact_label(fact: ExtractedFact) -> str:
    return f"fact {fact.local_id!r}"


def _create(
    fact: ExtractedFact, evidence_id: int, rejected: list[RejectedItem]
) -> CreateEntity | None:
    try:
        return CreateEntity(
            kind=fact.kind,
            name=fact.name,
            summary=fact.summary,
            attributes=fact.attributes,
            evidence_id=evidence_id,
        )
    except ValidationError as error:
        rejected.append(RejectedItem(_fact_label(fact), _first_error(error)))
        return None


def _add_edge(
    edge: ExtractedEdge,
    evidence_id: int,
    refs: dict[str, OpRef],
    dead: set[str],
    rejected: list[RejectedItem],
) -> AddEdge | None:
    label = f"edge {edge.src} -[{edge.rel}]-> {edge.dst}"
    ends: list[EntityRef] = []
    for end in (edge.src, edge.dst):
        if isinstance(end, int):
            ends.append(end)
        elif end in refs:
            ends.append(refs[end])
        else:
            reason = f"rejected fact {end!r}" if end in dead else f"unknown local id {end!r}"
            rejected.append(RejectedItem(label, reason))
            return None
    try:
        return AddEdge(
            src=ends[0],
            rel=edge.rel,
            dst=ends[1],
            started_at=edge.started_at,
            ended_at=edge.ended_at,
            note=edge.note,
            evidence_id=evidence_id,
        )
    except ValidationError as error:
        rejected.append(RejectedItem(label, _first_error(error)))
        return None


def _first_error(error: ValidationError) -> str:
    first = error.errors()[0]
    return str(first["msg"])
