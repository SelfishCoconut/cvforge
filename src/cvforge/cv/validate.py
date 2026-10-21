"""Check a stored CV against the knowledge base before it is presented (FR-24, FR-29).

Nothing is trusted from the CV's own rows. Each claim's text is recomputed from the live
knowledge base and compared; its assertion must exist and be about its entity; its entity
must still be confirmed. A CV with any issue cannot be marked final.
"""

from dataclasses import dataclass

import sqlalchemy as sa

from cvforge.cv.facts import claim_source
from cvforge.cv.store import StoredClaim, StoredCv
from cvforge.kb import queries
from cvforge.kb.vocab import KnowledgeState, TargetKind


@dataclass(frozen=True)
class Issue:
    """One problem found in a CV.

    Attributes:
        code: A stable machine name (`unsupported`, `text_mismatch`, `inactive_entity`, ...).
        message: What is wrong, for people.
        claim_id: The claim concerned, if the problem is about one.
    """

    code: str
    message: str
    claim_id: int | None = None


def _claim_issues(conn: sa.Connection, claim: StoredClaim) -> list[Issue]:
    assertion = queries.get_assertion(conn, claim.assertion_id)
    if (
        assertion is None
        or assertion.target_kind != TargetKind.ENTITY.value
        or assertion.target_id != claim.entity_id
    ):
        return [Issue("unsupported", f"{claim.text!r} has no assertion about its entity", claim.id)]
    entity = queries.get_entity(conn, claim.entity_id)
    if entity is None or entity.state is not KnowledgeState.CONFIRMED:
        state = "missing" if entity is None else entity.state.value
        return [
            Issue("inactive_entity", f"{claim.text!r} rests on an entity that is {state}", claim.id)
        ]
    source = claim_source(conn, claim.entity_id, claim.basis)
    if source is None or source[0] != claim.text:
        return [
            Issue("text_mismatch", f"{claim.text!r} no longer matches the stored fact", claim.id)
        ]
    return []


def validate_cv(engine: sa.Engine, cv: StoredCv) -> list[Issue]:
    """Validate a CV against the live knowledge base.

    Args:
        engine: The knowledge-base engine.
        cv: The stored CV.

    Returns:
        Every issue found; empty means the CV may be presented.
    """
    with engine.connect() as conn:
        return [issue for claim in cv.claims for issue in _claim_issues(conn, claim)]
