"""The app's startup wiring of the similarity index (FR-05, D-D).

An app that owns its database builds an embedder from the persisted settings and
catches the index up on startup. These tests keep that path off the network: the
embedder factory is replaced, and `open_database` hands back an already-seeded engine.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge import app as app_module
from cvforge.app import _build_embedder, create_app
from cvforge.config import Settings
from cvforge.kb import apply
from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider, OllamaEmbeddingProvider
from cvforge.llm.settings_store import ProviderSettings

pytestmark = pytest.mark.integration

Propose = Callable[..., int]


class _DownEmbedder:
    """Down before its dimension was ever probed, so `reindex_missing` itself raises."""

    @property
    def dimension(self) -> int:
        raise EmbeddingError("the embedding endpoint is down")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("the embedding endpoint is down")


@pytest.fixture
def seeded_app_settings(
    kb: sa.Engine, propose: Propose, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Settings, int]:
    """Settings for an app whose (patched) `open_database` returns a one-entity engine."""
    result = apply.commit_proposal(
        kb,
        propose({"op_type": "create_entity", "kind": "skill", "name": "rust"}, accept=True),
    )
    monkeypatch.setattr(app_module, "open_database", lambda *_args: kb)
    return Settings(frontend_dist=tmp_path / "none", data_dir=tmp_path / "data"), result.entity_ids[
        0
    ]


def _indexed(kb: sa.Engine) -> set[int]:
    with kb.connect() as conn:
        return {r[0] for r in conn.exec_driver_sql("SELECT entity_id FROM entity_vec")}


def test_startup_indexes_entities_the_index_is_missing(
    kb: sa.Engine,
    seeded_app_settings: tuple[Settings, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, entity_id = seeded_app_settings
    monkeypatch.setattr(app_module, "_build_embedder", lambda _s: FakeEmbeddingProvider(8))

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").status_code == 200
        assert entity_id in _indexed(kb)  # inside: shutdown disposes the engine


def test_an_unavailable_embedder_is_logged_and_never_blocks_startup(
    seeded_app_settings: tuple[Settings, int],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings, _ = seeded_app_settings
    monkeypatch.setattr(app_module, "_build_embedder", lambda _s: _DownEmbedder())

    with caplog.at_level("WARNING"):
        with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
            assert client.get("/api/health").status_code == 200

    assert "startup similarity reindex skipped" in caplog.text


def test_an_owned_engine_gets_an_ollama_embedder_and_an_injected_one_gets_none(
    kb: sa.Engine,
    seeded_app_settings: tuple[Settings, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, _ = seeded_app_settings
    monkeypatch.setattr(app_module, "reindex_missing", lambda *_a: 0)  # no probe, no network

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert isinstance(client.app.state.embedder, OllamaEmbeddingProvider)  # type: ignore[attr-defined]

    with TestClient(create_app(settings, engine=kb), base_url="http://127.0.0.1") as client:
        assert client.app.state.embedder is None  # type: ignore[attr-defined]


def test_the_embedder_falls_back_to_the_default_ollama_host() -> None:
    embedder: EmbeddingProvider = _build_embedder(ProviderSettings(base_url=None))

    assert isinstance(embedder, OllamaEmbeddingProvider)
    assert embedder._base_url == "http://127.0.0.1:11434"
