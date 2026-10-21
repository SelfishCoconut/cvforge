"""FR-30: undocumented requirements raise targeted questions; answers become proposals only."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from tests.support.profile import build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import queries

ANSWER = "I used Python for three years at Acme building ETL jobs."
FACT = {"local_id": "p", "kind": "skill", "name": "Python"}


@pytest.fixture
def discovery(kb: sa.Engine, propose: Any, tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    build_profile(kb, propose)  # Python recorded but never used; Haskell a gap; Fortran unknown
    posting = matched_posting(kb, "Rust", "Python", "Fortran", "Haskell")
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=kb)
    app.state.model_factory = lambda _e: TestModel(
        custom_output_args={"reply": "Noted.", "facts": [FACT], "edges": []}
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, posting


def _requirement(client: TestClient, posting: int, text: str) -> int:
    gaps = client.get(f"/api/jobs/{posting}/gaps").json()
    return int(next(g["requirement_id"] for g in gaps if g["text"] == text))


def test_an_undocumented_requirement_gets_a_question_that_names_it(
    discovery: tuple[TestClient, int],
) -> None:
    client, posting = discovery
    questions = client.get(f"/api/jobs/{posting}/discovery").json()

    assert [q["requirement_text"] for q in questions] == ["Python"]
    assert questions[0]["verdict"] == "undocumented"
    assert "“Python”" in questions[0]["text"] and "recorded but no use" in questions[0]["text"]


def test_gaps_and_backed_requirements_raise_no_discovery_question(
    discovery: tuple[TestClient, int],
) -> None:
    client, posting = discovery
    asked = {q["requirement_text"] for q in client.get(f"/api/jobs/{posting}/discovery").json()}
    assert asked.isdisjoint({"Fortran", "Haskell", "Rust"})
    fortran = _requirement(client, posting, "Fortran")
    url = f"/api/jobs/{posting}/discovery/{fortran}"
    assert client.post(f"{url}/answer", json={"answer": "I know it"}).status_code == 409
    assert client.post(f"{url}/decline").status_code == 409
    assert client.get("/api/jobs/999/discovery").status_code == 404


def test_answering_records_a_pending_proposal_and_writes_no_knowledge(
    discovery: tuple[TestClient, int], kb: sa.Engine
) -> None:
    client, posting = discovery
    python = _requirement(client, posting, "Python")
    with kb.connect() as conn:
        before = queries.table_counts(conn)

    response = client.post(
        f"/api/jobs/{posting}/discovery/{python}/answer", json={"answer": ANSWER}
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["id"] is not None and proposal["operations"]
    with kb.connect() as conn:
        after = queries.table_counts(conn)
        record = queries.get_proposal(conn, proposal["id"])
    assert (after["entity"], after["edge"], after["assertion"]) == (
        before["entity"],
        before["edge"],
        before["assertion"],
    )
    assert record is not None and record.status == "open" and record.origin == "chat"
    assert after["evidence"] == before["evidence"] + 1


def test_declining_changes_nothing_at_all(discovery: tuple[TestClient, int], kb: sa.Engine) -> None:
    client, posting = discovery
    python = _requirement(client, posting, "Python")
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    assert client.post(f"/api/jobs/{posting}/discovery/{python}/decline").status_code == 204
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before


def test_a_blank_answer_is_refused_and_records_nothing(
    discovery: tuple[TestClient, int], kb: sa.Engine
) -> None:
    client, posting = discovery
    python = _requirement(client, posting, "Python")
    with kb.connect() as conn:
        before = queries.table_counts(conn)
    response = client.post(f"/api/jobs/{posting}/discovery/{python}/answer", json={"answer": "   "})
    assert response.status_code == 422
    with kb.connect() as conn:
        assert queries.table_counts(conn) == before


def test_a_failing_model_is_a_502_after_the_answer_is_kept_as_provenance(
    discovery: tuple[TestClient, int],
) -> None:
    client, posting = discovery

    def broken(_engine: object) -> object:
        raise RuntimeError("model down")

    client.app.state.model_factory = broken  # type: ignore[attr-defined]
    python = _requirement(client, posting, "Python")
    response = client.post(
        f"/api/jobs/{posting}/discovery/{python}/answer", json={"answer": ANSWER}
    )
    assert response.status_code == 502
