"""`POST /api/documents/{id}/extract` records a pending proposal, then review commits it (FR-15)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from tests.support.documents import pdf_bytes

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import queries

FACT = {
    "local_id": "s",
    "kind": "skill",
    "name": "Rust",
    "excerpt": "Built a log parser in Rust",
}
PDF = pdf_bytes("Built a log parser in Rust.")


@pytest.fixture
def docs_client(kb: sa.Engine, tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")
    with TestClient(create_app(settings, engine=kb), base_url="http://127.0.0.1") as client:
        yield client


def _upload(client: TestClient) -> int:
    response = client.post("/api/documents", files={"file": ("cv.pdf", PDF)})
    source_id: int = response.json()["source_id"]
    return source_id


def _use(client: TestClient, output: dict[str, Any]) -> None:
    client.app.state.model_factory = lambda _e: TestModel(custom_output_args=output)  # type: ignore[attr-defined]


def test_upload_extract_review_commit_is_the_whole_loop(
    docs_client: TestClient, kb: sa.Engine
) -> None:
    source_id = _upload(docs_client)
    _use(docs_client, {"facts": [FACT], "edges": []})

    body = docs_client.post(f"/api/documents/{source_id}/extract").json()

    proposal = body["proposal"]
    (op,) = proposal["operations"]
    assert op["classification"] == "new" and body["rejected"] == []
    with kb.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 0
    review = f"/api/proposals/{proposal['id']}/operations/{op['id']}/review"
    docs_client.post(review, json={"decision": "accept"}).raise_for_status()
    docs_client.post(f"/api/proposals/{proposal['id']}/commit").raise_for_status()
    with kb.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 1


def test_the_committed_fact_cites_the_page_and_span(docs_client: TestClient, kb: sa.Engine) -> None:
    source_id = _upload(docs_client)
    _use(docs_client, {"facts": [FACT], "edges": []})
    docs_client.post(f"/api/documents/{source_id}/extract")

    with kb.connect() as conn:
        rows = conn.execute(sa.text("select locator, excerpt from evidence")).all()
    assert [(r.locator, r.excerpt) for r in rows] == [
        ("page:1 chars:0-26", "Built a log parser in Rust")
    ]


def test_a_quote_not_in_the_document_is_reported_not_proposed(docs_client: TestClient) -> None:
    source_id = _upload(docs_client)
    _use(docs_client, {"facts": [{**FACT, "excerpt": "Led a team of forty"}], "edges": []})

    body = docs_client.post(f"/api/documents/{source_id}/extract").json()

    assert body["proposal"]["operations"] == []
    assert body["rejected"][0]["reason"] == "no resolvable locator"


def test_an_unknown_document_is_a_404(docs_client: TestClient) -> None:
    assert docs_client.post("/api/documents/999/extract").status_code == 404


def test_a_model_failure_is_a_502_and_leaves_no_proposal(
    docs_client: TestClient, kb: sa.Engine
) -> None:
    source_id = _upload(docs_client)

    def boom(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError("endpoint down")

    docs_client.app.state.model_factory = lambda _e: FunctionModel(boom)  # type: ignore[attr-defined]

    response = docs_client.post(f"/api/documents/{source_id}/extract")

    assert response.status_code == 502 and "endpoint down" in response.json()["detail"]
    with kb.connect() as conn:
        assert queries.table_counts(conn)["proposal"] == 0
