"""A deterministic, network-free stand-in for `cvforge.kb.embeddings.EmbeddingProvider`."""

import hashlib
from collections.abc import Sequence


def _hash_floats(seed: str, n: int) -> list[float]:
    """`n` deterministic floats in `[0, 1)`, derived from `seed`."""
    values: list[float] = []
    counter = 0
    while len(values) < n:
        digest = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        for offset in range(0, len(digest), 4):
            if len(values) >= n:
                break
            values.append(int.from_bytes(digest[offset : offset + 4], "big") / 2**32)
        counter += 1
    return values


class FakeEmbeddingProvider:
    """A hash-based embedding provider for tests: same text always yields the same vector.

    Each vector is split into a leading half seeded by the text's first word and a
    trailing half seeded by the whole text, so two texts sharing a leading word land
    closer together in cosine similarity than two unrelated texts — enough to make a
    similarity-threshold test meaningful without a real model.
    """

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        leading_n = max(1, self._dimension // 2)
        vectors = []
        for text in texts:
            words = text.strip().lower().split()
            leading_seed = words[0] if words else ""
            leading = _hash_floats(f"leading:{leading_seed}", leading_n)
            tail = _hash_floats(f"tail:{text}", self._dimension - leading_n)
            vectors.append(leading + tail)
        return vectors
