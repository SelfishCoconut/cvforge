"""`/api/jobs/{id}/cvs` and `/api/cvs/{id}`: generate, read, resolve a claim, validate, finalise."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.profile import build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.jobs.store import persist_posting
from cvforge.kb import schema
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage


@pytest.fixture
def cvs(kb: sa.Engine, propose: Any, tmp_path: Path) -> Iterator[tuple[TestClient, int, Any]]:
    profile = build_profile(kb, propose)
    posting = matched_posting(kb, "Rust", "Fortran")
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    with TestClient(create_app(settings, engine=kb), base_url="http://127.0.0.1") as client:
        yield client, posting, profile


def test_generating_returns_a_draft_with_sections_and_claims(
    cvs: tuple[TestClient, int, Any],
) -> None:
    client, posting, _ = cvs
    response = client.post(f"/api/jobs/{posting}/cvs", json={})

    assert response.status_code == 201
    body = response.json()
    assert (body["version"], body["status"], body["generation_mode"]) == (1, "draft", "automatic")
    assert [s["title"] for s in body["sections"]] == [
        "Skills",
        "Experience",
        "Education",
        "Certifications",
    ]
    assert "Fortran" not in str(body)


def test_a_posting_that_was_never_matched_is_refused(
    cvs: tuple[TestClient, int, Any], kb: sa.Engine
) -> None:
    client, _, _ = cvs
    page = FetchedPage("https://j.test/9", "https://j.test/9", "J", "t", "static")
    unmatched = persist_posting(kb, page, JobAnalysis(required_skills=["Rust"])).id
    assert client.post(f"/api/jobs/{unmatched}/cvs", json={}).status_code == 409
    assert client.post("/api/jobs/999/cvs", json={}).status_code == 404


def test_a_claim_resolves_to_its_stored_fact_and_evidence(
    cvs: tuple[TestClient, int, Any],
) -> None:
    client, posting, _ = cvs
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
    claim = cv["sections"][0]["items"][0]["claims"][0]

    detail = client.get(f"/api/cvs/{cv['id']}/claims/{claim['id']}").json()

    assert detail["entity_name"] == "Rust" and detail["entity_state"] == "confirmed"
    assert detail["evidence"]["excerpt"] and detail["evidence"]["locator"]
    assert client.get(f"/api/cvs/{cv['id']}/claims/99999").status_code == 404


def test_reads_and_lists(cvs: tuple[TestClient, int, Any]) -> None:
    client, posting, _ = cvs
    first = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
    second = client.post(f"/api/jobs/{posting}/cvs", json={"parent_cv_id": first["id"]}).json()

    assert client.get(f"/api/cvs/{second['id']}").json()["parent_cv_id"] == first["id"]
    assert [c["version"] for c in client.get(f"/api/jobs/{posting}/cvs").json()] == [1, 2]
    assert client.get("/api/cvs/999").status_code == 404
    assert client.post(f"/api/jobs/{posting}/cvs", json={"parent_cv_id": 999}).status_code == 404


def test_a_valid_cv_can_be_made_final(cvs: tuple[TestClient, int, Any]) -> None:
    client, posting, _ = cvs
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()

    assert client.post(f"/api/cvs/{cv['id']}/validate").json() == {"valid": True, "issues": []}
    final = client.post(f"/api/cvs/{cv['id']}/final")
    assert final.status_code == 200 and final.json()["status"] == "final"


def test_an_invalid_cv_cannot_be_made_final(
    cvs: tuple[TestClient, int, Any], kb: sa.Engine
) -> None:
    client, posting, _ = cvs
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
    with kb.begin() as conn:
        conn.execute(
            sa.update(schema.cv_claim)
            .where(schema.cv_claim.c.text == "Rust")
            .values(text="Rust guru")
        )

    report = client.post(f"/api/cvs/{cv['id']}/validate").json()
    assert report["valid"] is False and report["issues"][0]["code"] == "text_mismatch"
    refused = client.post(f"/api/cvs/{cv['id']}/final")
    assert refused.status_code == 409
    assert client.get(f"/api/cvs/{cv['id']}").json()["status"] == "draft"


def test_generating_writes_no_knowledge(cvs: tuple[TestClient, int, Any], kb: sa.Engine) -> None:
    client, posting, _ = cvs
    with kb.connect() as conn:
        before = [
            conn.execute(sa.select(sa.func.count()).select_from(t)).scalar()
            for t in (schema.entity, schema.edge, schema.assertion, schema.proposal)
        ]
    client.post(f"/api/jobs/{posting}/cvs", json={})
    with kb.connect() as conn:
        after = [
            conn.execute(sa.select(sa.func.count()).select_from(t)).scalar()
            for t in (schema.entity, schema.edge, schema.assertion, schema.proposal)
        ]
    assert after == before
