"""FR-05 / D-D: committing a proposal indexes its new entities, or reports index_pending."""

from collections.abc import Callable, Sequence

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.app import create_app
from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider, find_similar

pytestmark = pytest.mark.integration

Propose = Callable[..., int]


class _FailingProvider:
    """An `EmbeddingProvider` whose `embed` always raises."""

    dimension = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("the embedding endpoint is down")


def _client(kb: sa.Engine, embedder: EmbeddingProvider | None) -> TestClient:
    return TestClient(create_app(engine=kb, embedder=embedder), base_url="http://127.0.0.1")


def test_committing_a_new_entity_indexes_it(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    proposal_id = propose(
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True
    )

    with _client(kb, provider) as client:
        response = client.post(f"/api/proposals/{proposal_id}/commit")

    assert response.status_code == 200
    assert response.json()["index_pending"] == []
    assert find_similar(kb, provider, "rust", threshold=0.0) != []


def test_a_failing_embedder_still_commits_and_reports_index_pending(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal_id = propose(
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True
    )

    with _client(kb, _FailingProvider()) as client:
        response = client.post(f"/api/proposals/{proposal_id}/commit")

    assert response.status_code == 200
    body = response.json()
    entity_id = body["entity_ids"]["0"]
    assert body["index_pending"] == [entity_id]


def test_no_embedder_configured_skips_indexing_without_error(
    kb: sa.Engine, propose: Propose
) -> None:
    proposal_id = propose(
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"}, accept=True
    )

    with _client(kb, None) as client:
        response = client.post(f"/api/proposals/{proposal_id}/commit")

    assert response.status_code == 200
    assert response.json()["index_pending"] == []
