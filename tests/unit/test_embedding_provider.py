import json
from collections.abc import Sequence

import httpx
import pytest
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider, OllamaEmbeddingProvider


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot: float = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a: float = sum(x * x for x in a) ** 0.5
    norm_b: float = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


def test_the_fake_returns_the_configured_dimension_deterministically() -> None:
    fake = FakeEmbeddingProvider(dimension=8)
    assert fake.dimension == 8
    first, second = fake.embed(["I use Rust", "I use Rust"])
    assert first == second
    assert len(first) == 8


def test_a_fake_of_another_dimension_works_with_no_edit_to_embeddings_py() -> None:
    fake = FakeEmbeddingProvider(dimension=16)
    assert isinstance(fake, EmbeddingProvider)
    assert fake.dimension == 16
    (vector,) = fake.embed(["anything"])
    assert len(vector) == 16


@pytest.mark.parametrize(
    ("shared_a", "shared_b", "unrelated"),
    [
        ("rust programmer", "rust developer", "banana bread recipe"),
        ("rust programmer", "rust enthusiast", "banana bread recipe"),
        ("python developer", "python programmer", "banana bread recipe"),
        ("rust programmer", "rust developer", "python developer"),
    ],
)
def test_two_texts_sharing_a_word_are_more_similar_than_unrelated_texts(
    shared_a: str, shared_b: str, unrelated: str
) -> None:
    fake = FakeEmbeddingProvider(dimension=8)
    a, b, c = fake.embed([shared_a, shared_b, unrelated])
    assert _cosine(a, b) > _cosine(a, c)


def test_an_object_missing_embed_is_not_an_embedding_provider() -> None:
    class NotAProvider:
        @property
        def dimension(self) -> int:
            return 8

    assert not isinstance(NotAProvider(), EmbeddingProvider)


def test_ollama_provider_posts_the_batch_and_parses_the_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaEmbeddingProvider("http://127.0.0.1:11434", "nomic-embed-text", client=client)

    result = provider.embed(["a", "b"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://127.0.0.1:11434/api/embed"
    assert captured["body"] == {"model": "nomic-embed-text", "input": ["a", "b"]}


def test_ollama_provider_wraps_an_http_error_status_as_embedding_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaEmbeddingProvider("http://127.0.0.1:11434", "nomic-embed-text", client=client)

    with pytest.raises(EmbeddingError):
        provider.embed(["a"])


def test_ollama_provider_dimension_is_probed_once_and_cached() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaEmbeddingProvider("http://127.0.0.1:11434", "nomic-embed-text", client=client)

    assert provider.dimension == 3
    assert provider.dimension == 3
    assert len(calls) == 1


def test_ollama_provider_wraps_a_connection_error_as_embedding_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaEmbeddingProvider("http://127.0.0.1:11434", "nomic-embed-text", client=client)

    with pytest.raises(EmbeddingError):
        provider.embed(["a"])
