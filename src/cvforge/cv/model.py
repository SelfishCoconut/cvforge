"""The structured CV: sections of items, every string of which is a claim (FR-24, FR-25).

A CV has no free text. Section titles are template structure; everything else is a
`ClaimDraft` copied from a stored fact and bound to the entity and assertion it came from.
"""

from dataclasses import dataclass

from cvforge.kb.vocab import ClaimBasis, ClaimSlot


@dataclass(frozen=True)
class ClaimDraft:
    """One line of a CV, before it is stored.

    Attributes:
        section: The section it belongs to (`Skills`, `Experience`, ...).
        item_index: Which item of the section.
        slot: Where in the item: header, subheader, period or bullet.
        position: Order among claims of the same slot in the item.
        basis: Which stored fact `text` is copied from.
        text: The rendered string, exactly the stored fact.
        entity_id: The entity the fact is about.
        assertion_id: The assertion that states the fact.
    """

    section: str
    item_index: int
    slot: ClaimSlot
    position: int
    basis: ClaimBasis
    text: str
    entity_id: int
    assertion_id: int
    link_assertion_id: int | None = None
