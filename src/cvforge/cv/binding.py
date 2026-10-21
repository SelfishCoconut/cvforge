"""Prove that a claim is what its assertion says (FR-24, FR-25, NFR-05, invariant 5).

The one rule shared by the store (before a claim is saved) and the validator (before a CV is
presented, finalised or sent): the claim's text must be exactly the fact `claim_source` copies
from the live knowledge base, and the assertion it cites must be the one whose recorded value
is that fact. A claim placed under another entity's header must also cite the edge that
relates the two.
"""

import sqlalchemy as sa

from cvforge.cv.facts import claim_source
from cvforge.cv.grounding import ungrounded_terms
from cvforge.kb import queries
from cvforge.kb.vocab import ClaimBasis, KnowledgeState, TargetKind


def claim_problem(
    conn: sa.Connection,
    *,
    text: str,
    entity_id: int,
    assertion_id: int,
    basis: ClaimBasis,
    link_assertion_id: int | None,
    header_entity_id: int | None,
) -> tuple[str, str] | None:
    """Return (code, message) if the claim is not fully supported, else None.

    Args:
        conn: An open connection.
        text: The claim's text.
        entity_id: The entity it says it is about.
        assertion_id: The assertion it cites.
        basis: Which fact it says it copies.
        link_assertion_id: The edge assertion justifying its place under its item's header.
        header_entity_id: The entity of that header, or None if the claim is not under one.

    Returns:
        None if the claim is supported; otherwise a stable code and a message.
    """
    assertion = queries.get_assertion(conn, assertion_id)
    if (
        assertion is None
        or assertion.target_kind != TargetKind.ENTITY.value
        or assertion.target_id != entity_id
    ):
        return "unsupported", f"{text!r} cites no assertion about its entity"
    entity = queries.get_entity(conn, entity_id)
    if entity is None or entity.state is not KnowledgeState.CONFIRMED:
        state = "missing" if entity is None else entity.state.value
        return "inactive_entity", f"{text!r} rests on an entity that is {state}"
    if basis is ClaimBasis.REWORD:
        return _reword_problem(
            conn, text, entity_id, assertion, link_assertion_id, header_entity_id
        )
    source = claim_source(conn, entity_id, basis)
    if source is None or source[0] != text:
        return "text_mismatch", f"{text!r} no longer matches the stored fact"
    if source[1] != assertion_id:
        return "wrong_assertion", f"{text!r} cites an assertion that does not state it"
    return _link_problem(conn, text, entity_id, link_assertion_id, header_entity_id)


def _facts_about(conn: sa.Connection, entity_id: int) -> list[str]:
    """Every stored text a line about the entity may draw on: its own and its neighbours' names."""
    record = queries.get_entity(conn, entity_id)
    if record is None:
        return []
    texts = [record.name, record.summary or "", *(str(v) for v in record.attributes.values())]
    for edge in queries.neighbours(conn, entity_id):
        other = queries.get_entity(conn, edge.dst_id if edge.src_id == entity_id else edge.src_id)
        if other is not None:
            texts.append(other.name)
    return texts


def _reword_problem(
    conn: sa.Connection,
    text: str,
    entity_id: int,
    assertion: queries.AssertionRecord,
    link_assertion_id: int | None,
    header_entity_id: int | None,
) -> tuple[str, str] | None:
    """A reworded claim keeps a name or summary assertion and adds no new fact."""
    if assertion.field not in ("name", "summary"):
        return "wrong_assertion", f"{text!r} rewords a fact its assertion does not state"
    novel = ungrounded_terms(_facts_about(conn, entity_id), text)
    if novel:
        return "ungrounded", f"{text!r} adds {novel}, which nothing stored about it says"
    return _link_problem(conn, text, entity_id, link_assertion_id, header_entity_id)


def _link_problem(
    conn: sa.Connection,
    text: str,
    entity_id: int,
    link_assertion_id: int | None,
    header_entity_id: int | None,
) -> tuple[str, str] | None:
    """A claim under another entity's header must cite the edge that relates them."""
    if header_entity_id is None or header_entity_id == entity_id:
        return None
    link = None if link_assertion_id is None else queries.get_assertion(conn, link_assertion_id)
    related = (
        link is not None
        and link.target_kind == TargetKind.EDGE.value
        and any(
            edge.id == link.target_id
            and {edge.src_id, edge.dst_id} == {header_entity_id, entity_id}
            for edge in queries.neighbours(conn, header_entity_id)
        )
    )
    if related:
        return None
    return "unlinked", f"{text!r} sits under another entity with no recorded relationship"
