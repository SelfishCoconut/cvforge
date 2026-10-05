"""Benchmark (NFR-10): the chat round-trip against a real local model.

Drives the real pipeline (the chat endpoint, the agent, intake) against the
configured **local** Ollama endpoint with an empty in-memory knowledge base, and
reports p50/p95 of message-to-proposal time. Exits non-zero when p95 exceeds 30 s,
and refuses to run against an external provider (NFR-10 criterion 3).

Not part of `make test` or CI: unit, integration and golden tests never call a
live model (NFR-08). Run it by hand: `uv run python scripts/bench/latency.py`.
"""

import argparse
import math
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from cvforge.kb.vocab import Provider
from cvforge.llm.settings_store import ProviderSettings

THRESHOLD_SECONDS = 30.0
FIXTURES = Path(__file__).parent / "fixtures" / "messages.txt"


class NotLocalError(Exception):
    """The configured provider is not a local Ollama endpoint."""


def percentile(values: Sequence[float], q: float) -> float:
    """Return the nearest-rank `q`th percentile (0 < q <= 100) of `values`.

    Args:
        values: The samples. Must not be empty.
        q: The percentile, in (0, 100].

    Returns:
        The sample at rank ``ceil(q/100 * n)``.

    Raises:
        ValueError: If `values` is empty or `q` is out of range.
    """
    if not values:
        raise ValueError("no samples")
    if not 0 < q <= 100:
        raise ValueError("q must be in (0, 100]")
    ordered = sorted(values)
    return ordered[math.ceil(q / 100 * len(ordered)) - 1]


def require_local(settings: ProviderSettings) -> None:
    """Refuse anything but Ollama on a loopback address.

    Args:
        settings: The provider settings the benchmark would run with.

    Raises:
        NotLocalError: For an external provider or a non-loopback endpoint.
    """
    if settings.provider is not Provider.OLLAMA:
        raise NotLocalError(f"{settings.provider} is an external provider; NFR-10 is local-only")
    host = urlparse(settings.base_url or "").hostname or ""
    if host != "localhost" and not _is_loopback(host):
        raise NotLocalError(f"{host or 'no host'} is not a loopback address")


def _is_loopback(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def measure(send: Callable[[str], None], messages: Sequence[str], runs: int) -> list[float]:
    """Time `send` for every message, `runs` times over.

    Args:
        send: Submits one message and returns when its proposal is stored.
        messages: The fixture messages.
        runs: How many passes over the fixtures.

    Returns:
        One duration in seconds per call.
    """
    durations: list[float] = []
    for _ in range(runs):
        for message in messages:
            start = time.perf_counter()
            send(message)
            durations.append(time.perf_counter() - start)
    return durations


@contextmanager
def _real_sender(model: str, base_url: str) -> Iterator[Callable[[str], None]]:
    """Build a sender over the real app, an empty in-memory database and local Ollama."""
    from fastapi.testclient import TestClient

    from cvforge.app import create_app
    from cvforge.kb.db import make_engine
    from cvforge.kb.embeddings import OllamaEmbeddingProvider
    from cvforge.kb.schema import metadata
    from cvforge.llm.settings_store import load_settings, save_settings

    engine = make_engine(None)
    metadata.create_all(engine)
    settings = load_settings(engine).model_copy(update={"model": model, "base_url": base_url})
    require_local(settings)
    save_settings(engine, settings)
    embedder = OllamaEmbeddingProvider(base_url, settings.embedding_model)
    app = create_app(engine=engine, embedder=embedder)

    with TestClient(app, base_url="http://127.0.0.1") as client:

        def send(text: str) -> None:
            client.post("/api/chat/messages", json={"text": text}).raise_for_status()

        yield send


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        0 when p95 is within the threshold, 1 above it, 2 when refusing to run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=ProviderSettings().model)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)
    messages = FIXTURES.read_text(encoding="utf-8").splitlines()
    try:
        with _real_sender(args.model, args.base_url) as send:
            durations = measure(send, messages, args.runs)
    except NotLocalError as error:
        print(f"refusing to run: {error}")
        return 2
    p50, p95 = percentile(durations, 50), percentile(durations, 95)
    print(f"model={args.model} samples={len(durations)} p50={p50:.1f}s p95={p95:.1f}s")
    return 0 if p95 <= THRESHOLD_SECONDS else 1


if __name__ == "__main__":
    raise SystemExit(main())
