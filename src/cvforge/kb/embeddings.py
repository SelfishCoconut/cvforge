"""Pluggable text embedding providers (FR-40).

The knowledge base never depends on a specific embedding backend directly: it
depends on `EmbeddingProvider`, so a different model or a different dimension
is a settings change, not a code change.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx


class EmbeddingError(Exception):
    """An embedding call failed: the network, the endpoint, or the model itself."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Something that turns text into fixed-length vectors."""

    @property
    def dimension(self) -> int:
        """The length of every vector this provider returns."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each of `texts`, in order.

        Args:
            texts: The strings to embed.

        Returns:
            One vector of length `dimension` per input text, same order.

        Raises:
            EmbeddingError: If the provider could not embed the batch.
        """
        ...


class OllamaEmbeddingProvider:
    """Embeds text through a local Ollama server's `/api/embed` endpoint."""

    def __init__(self, base_url: str, model: str, *, client: httpx.Client | None = None) -> None:
        """Build a provider bound to one Ollama server and model.

        Args:
            base_url: The bare Ollama host, e.g. `http://127.0.0.1:11434` (no
                trailing `/api/...`).
            model: The embedding model name Ollama should load.
            client: An `httpx.Client` to use instead of building one; tests
                inject a client over `httpx.MockTransport`.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client()
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        """The vector length, probed once with a one-word embed call and cached."""
        if self._dimension is None:
            self._dimension = len(self.embed(["."])[0])
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """POST `{base_url}/api/embed` and return the embeddings it reports.

        Args:
            texts: The strings to embed.

        Returns:
            One vector per input text, same order as Ollama returned them.

        Raises:
            EmbeddingError: On any transport error or non-2xx response.
        """
        try:
            response = self._client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": list(texts)},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding call to {self._base_url} failed: {exc}") from exc
        return list(response.json()["embeddings"])
