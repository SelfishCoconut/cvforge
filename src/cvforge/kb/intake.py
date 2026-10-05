"""Intake: the one call that turns extracted payloads into a stored proposal (FR-07).

This module constructs no write and reads nothing itself; storage is
`apply.record_proposal`'s job (invariant 2). It exists so the chat handler has a
single call, so an empty batch never touches the database, and so an embedding
outage degrades to "no similarity" instead of failing the whole message.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa

from cvforge.kb import apply
from cvforge.kb.classify import SimilarFinder
from cvforge.kb.embeddings import EmbeddingError
from cvforge.kb.models import OperationInput, Payload, ProposalInput
from cvforge.kb.vocab import EntityKind, Origin


@dataclass(frozen=True)
class Intake:
    """A stored proposal and whether duplicate detection could run for it."""

    proposal_id: int
    similarity_available: bool


def propose(
    engine: sa.Engine,
    *,
    origin: Origin,
    source_id: int,
    summary: str,
    payloads: Sequence[Payload],
    similar: SimilarFinder | None = None,
) -> Intake | None:
    """Store one proposal from these payloads.

    Args:
        engine: The knowledge-base engine.
        origin: Where the proposal came from.
        source_id: The source every payload's evidence belongs to.
        summary: A one-line description shown at review.
        payloads: The typed operations, in dependency order.
        similar: Optional similarity lookup. If it raises `EmbeddingError` the
            proposal is stored without similarity and `similarity_available` is
            False; any other exception propagates and nothing is stored.

    Returns:
        The stored proposal, or None when `payloads` is empty (nothing is written).

    Raises:
        ValidationError: If a payload refers to an operation that is not an
            earlier `create_entity` in this batch.
    """
    if not payloads:
        return None
    draft = ProposalInput(
        origin=origin,
        source_id=source_id,
        summary=summary,
        operations=[OperationInput(seq=seq, payload=item) for seq, item in enumerate(payloads)],
    )
    tracker = _Tracking(similar)
    proposal_id = apply.record_proposal(engine, draft, similar=tracker if similar else None)
    return Intake(proposal_id, similarity_available=not tracker.failed)


class _Tracking:
    """Wraps a finder so an embedding failure means "no match", and is remembered."""

    def __init__(self, inner: SimilarFinder | None) -> None:
        self._inner = inner
        self.failed = False

    def __call__(self, kind: EntityKind, name: str) -> int | None:
        if self._inner is None or self.failed:
            return None
        try:
            return self._inner(kind, name)
        except EmbeddingError:
            self.failed = True
            return None
