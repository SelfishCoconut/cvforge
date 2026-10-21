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


def test_rendering_an_invalid_cv_is_refused_and_a_valid_one_needs_no_latex_here(
    cvs: tuple[TestClient, int, Any],
    kb: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, posting, _ = cvs
    client.app.state.settings.cv_out_dir = tmp_path / "out"  # type: ignore[attr-defined]
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()

    def fake_compile(tex: Path) -> Path:
        pdf = tex.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-fake")
        return pdf

    monkeypatch.setattr("cvforge.api.cvs.compile_pdf", fake_compile)
    assert client.get(f"/api/cvs/{cv['id']}/files/pdf").status_code == 404
    done = client.post(f"/api/cvs/{cv['id']}/render")
    assert (
        done.status_code == 200 and client.get(f"/api/cvs/{cv['id']}/files/tex").status_code == 200
    )

    with kb.begin() as conn:
        conn.execute(
            sa.update(schema.cv_claim).where(schema.cv_claim.c.text == "Rust").values(text="Rust+")
        )
    assert client.post(f"/api/cvs/{cv['id']}/render").status_code == 409


def test_a_latex_failure_is_a_502_not_a_corrupt_file(
    cvs: tuple[TestClient, int, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cvforge.cv.compile import CompileError

    client, posting, _ = cvs
    client.app.state.settings.cv_out_dir = tmp_path / "out"  # type: ignore[attr-defined]
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()

    def fail(tex: Path) -> Path:
        raise CompileError("LaTeX failed (exit 1): ! Missing $ inserted.")

    monkeypatch.setattr("cvforge.api.cvs.compile_pdf", fail)
    response = client.post(f"/api/cvs/{cv['id']}/render")

    assert response.status_code == 502 and "Missing $" in response.json()["detail"]
    assert client.get(f"/api/cvs/{cv['id']}/files/pdf").status_code == 404


def test_lineage_and_applications_over_http(cvs: tuple[TestClient, int, Any]) -> None:
    client, posting, _ = cvs
    first = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
    second = client.post(f"/api/jobs/{posting}/cvs", json={"parent_cv_id": first["id"]}).json()
    assert [c["id"] for c in client.get(f"/api/cvs/{second['id']}/lineage").json()] == [
        first["id"],
        second["id"],
    ]
    assert client.get("/api/cvs/999/lineage").status_code == 404

    body = {"job_posting_id": posting, "cv_id": second["id"], "applied_at": "2026-10-21T09:30:00"}
    assert client.post("/api/applications", json=body).status_code == 422  # still a draft
    client.post(f"/api/cvs/{second['id']}/final")
    created = client.post("/api/applications", json=body)
    assert created.status_code == 201 and created.json()["status"] == "applied"

    used = client.get("/api/applications", params={"cv_id": second["id"]}).json()
    assert [a["id"] for a in used] == [created.json()["id"]]
    moved = client.post(
        f"/api/applications/{created.json()['id']}/status", json={"status": "offer"}
    )
    assert moved.json()["status"] == "offer"
    assert client.post("/api/applications/999/status", json={"status": "offer"}).status_code == 404
    assert client.post("/api/applications", json={**body, "cv_id": 999}).status_code == 404
    assert client.post("/api/applications", json={**body, "status": "ghosted"}).status_code == 422


def test_a_parent_from_another_posting_is_a_422(
    cvs: tuple[TestClient, int, Any], kb: sa.Engine
) -> None:
    client, posting, _ = cvs
    first = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
    page = FetchedPage("https://j.test/77", "https://j.test/77", "J", "t", "static")
    other = persist_posting(kb, page, JobAnalysis()).id
    response = client.post(f"/api/jobs/{other}/cvs", json={"parent_cv_id": first["id"]})
    assert response.status_code == 422
