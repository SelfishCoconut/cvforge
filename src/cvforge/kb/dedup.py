"""A real `SimilarFinder` (`kb.classify`) over the sqlite-vec index (D-D).

This module constructs no writes and reads nothing from a knowledge table
itself, so it needs no registered-writer entry (ADR-0011).
"""

import sqlalchemy as sa

from cvforge.kb.classify import SimilarFinder
from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider, find_similar
from cvforge.kb.vocab import EntityKind


def make_similar_finder(
    engine: sa.Engine, provider: EmbeddingProvider, threshold: float
) -> SimilarFinder:
    """Build a `SimilarFinder` backed by `find_similar`.

    Degrades to "nothing found" rather than raising when the embedder is
    unavailable: `classify()` then falls back to `new`, so a down embedding
    endpoint never blocks classification, only makes it more conservative.

    Args:
        engine: The knowledge-base engine.
        provider: What turns a name into a vector.
        threshold: The minimum cosine similarity to count as the same thing.

    Returns:
        A finder suitable for `kb.classify.classify`'s `similar` argument.
    """

    def find(kind: EntityKind, name: str) -> int | None:
        try:
            hits = find_similar(engine, provider, name, kind=kind, threshold=threshold, limit=1)
        except EmbeddingError:
            return None
        return hits[0].entity_id if hits else None

    return find
