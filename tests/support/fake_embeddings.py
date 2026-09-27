"""A deterministic, network-free stand-in for `cvforge.kb.embeddings.EmbeddingProvider`."""

import hashlib
from collections.abc import Sequence


def _hash_floats(seed: str, n: int) -> list[float]:
    """`n` deterministic floats in `[-1, 1)`, derived from `seed`."""
    values: list[float] = []
    counter = 0
    while len(values) < n:
        digest = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        for offset in range(0, len(digest), 4):
            if len(values) >= n:
                break
            values.append(2 * (int.from_bytes(digest[offset : offset + 4], "big") / 2**32) - 1)
        counter += 1
    return values


class FakeEmbeddingProvider:
    """A hash-based bag-of-words embedding provider for tests.

    Same text always yields the same vector: each word gets its own deterministic
    vector (components in `[-1, 1)`, so unrelated words are uncorrelated rather than
    all pulling the same way), and a text's vector is the sum of its words' vectors.
    Two texts sharing a word are therefore reliably more cosine-similar than two that
    share none — enough to make a similarity-threshold test meaningful without a real
    model.
    """

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            words = text.strip().lower().split() or [""]
            summed = [0.0] * self._dimension
            for word in words:
                for i, component in enumerate(_hash_floats(f"word:{word}", self._dimension)):
                    summed[i] += component
            vectors.append(summed)
        return vectors
