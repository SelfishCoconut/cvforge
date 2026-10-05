"""FR-05 / D-D: committing a proposal indexes its new entities, or reports index_pending."""

from collections.abc import Callable, Sequence

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.app import create_app
from cvforge.kb import apply
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


@pytest.mark.parametrize(
    ("field", "value", "probe"),
    [
        ("name", "pastry chef", "pastry chef"),
        ("summary", "bakes sourdough", "rust programmer bakes sourdough"),
    ],
)
def test_renaming_or_resummarising_reindexes_the_entity(
    kb: sa.Engine, propose: Propose, field: str, value: str, probe: str
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    create = {"op_type": "create_entity", "kind": "role", "name": "rust programmer"}
    with _client(kb, provider) as client:
        created = client.post(f"/api/proposals/{propose(create, accept=True)}/commit").json()
        entity_id = created["entity_ids"]["0"]
        change = {"op_type": "update_field", "entity_id": entity_id, "field": field, "value": value}
        response = client.post(f"/api/proposals/{propose(change, accept=True)}/commit")

    assert response.status_code == 200, response.text
    assert response.json()["index_pending"] == []
    hits = find_similar(kb, provider, probe, threshold=0.99)
    assert [hit.entity_id for hit in hits] == [entity_id]


def test_a_reindex_that_fails_is_reported_as_index_pending(kb: sa.Engine, propose: Propose) -> None:
    created = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "role", "name": "chef"}, accept=True)
    )
    entity_id = created.entity_ids[0]
    rename = {"op_type": "update_field", "entity_id": entity_id, "field": "name", "value": "baker"}
    proposal_id = propose(rename, accept=True)

    with _client(kb, _FailingProvider()) as client:
        response = client.post(f"/api/proposals/{proposal_id}/commit")

    assert response.json()["index_pending"] == [entity_id]
