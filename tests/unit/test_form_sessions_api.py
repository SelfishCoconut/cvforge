"""FR-36/FR-37 over HTTP: sessions suggest from the CV, fill only what was confirmed."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.profile import build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.cv.generate import generate_cv
from cvforge.cv.store import save_cv
from cvforge.forms.fill import FillReport
from cvforge.forms.store import StoredSession
from cvforge.web.fetch import FetchError

FORM = """<form><label for=y>Years of experience</label><input id=y name=y>
<label for=c>Favourite colour</label><input id=c name=c></form>"""
URL = "https://x.test/apply"
FILLED: list[StoredSession] = []


def _filler(session: StoredSession) -> FillReport:
    FILLED.append(session)
    return FillReport(("f1",), (("f2", "the page changed since the form was analysed"),))


@pytest.fixture
def forms(kb: sa.Engine, tmp_path: Path, propose: Any) -> Iterator[TestClient]:
    FILLED.clear()
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    save_cv(kb, posting, generate_cv(kb, posting))
    app = create_app(Settings(data_dir=tmp_path / "d", frontend_dist=tmp_path / "n"), engine=kb)
    app.state.form_html_fetcher = lambda url: FORM
    app.state.form_filler = _filler
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _start(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/forms/fills", json={"url": URL, "cv_id": 1})
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def test_a_session_lists_fields_with_unconfirmed_suggestions(forms: TestClient) -> None:
    session = _start(forms)
    assert session["status"] == "analyzed" and session["cv_id"] == 1
    colour = session["fields"][1]
    assert colour["suggested"] is None and not colour["confirmed"]
    assert "selector" not in colour
    assert forms.get(f"/api/forms/fills/{session['id']}").json() == session


def test_a_session_needs_a_real_cv_and_a_form(forms: TestClient) -> None:
    missing = forms.post("/api/forms/fills", json={"url": URL, "cv_id": 99})
    assert missing.status_code == 404
    forms.app.state.form_html_fetcher = lambda url: "<p>none</p>"  # type: ignore[attr-defined]
    assert forms.post("/api/forms/fills", json={"url": URL, "cv_id": 1}).status_code == 422

    def refuse(url: str) -> str:
        raise FetchError("refused")

    forms.app.state.form_html_fetcher = refuse  # type: ignore[attr-defined]
    assert forms.post("/api/forms/fills", json={"url": URL, "cv_id": 1}).status_code == 422


def test_confirm_edit_and_withdraw(forms: TestClient) -> None:
    sid = _start(forms)["id"]
    path = f"/api/forms/fills/{sid}/fields/f2"
    confirmed = forms.put(path, json={"value": "teal"}).json()
    assert confirmed["fields"][1]["confirmed_value"] == "teal"
    assert forms.delete(path).json()["fields"][1]["confirmed"] is False
    assert forms.put(f"/api/forms/fills/{sid}/fields/f9", json={"value": "x"}).status_code == 409
    assert forms.put("/api/forms/fills/99/fields/f1", json={"value": "x"}).status_code == 404
    assert forms.delete("/api/forms/fills/99/fields/f1").status_code == 404
    assert forms.delete(f"/api/forms/fills/{sid}/fields/f9").status_code == 409
    assert forms.get("/api/forms/fills/99").status_code == 404


def test_filling_needs_a_confirmation_and_happens_once(forms: TestClient) -> None:
    sid = _start(forms)["id"]
    fill = f"/api/forms/fills/{sid}/fill"
    assert forms.post(fill).status_code == 409 and FILLED == []

    forms.put(f"/api/forms/fills/{sid}/fields/f2", json={"value": "teal"})
    result = forms.post(fill).json()
    assert result == {
        "filled": ["f1"],
        "skipped": {"f2": "the page changed since the form was analysed"},
    }
    assert [f["key"] for f in FILLED[0].fields if f["confirmed"]] == ["f2"]
    assert forms.get(f"/api/forms/fills/{sid}").json()["status"] == "filled"
    assert forms.post(fill).status_code == 409
    assert forms.put(f"/api/forms/fills/{sid}/fields/f1", json={"value": "1"}).status_code == 409
    assert forms.post("/api/forms/fills/99/fill").status_code == 404


def test_a_failed_fill_leaves_the_session_fillable(forms: TestClient) -> None:
    sid = _start(forms)["id"]
    forms.put(f"/api/forms/fills/{sid}/fields/f2", json={"value": "teal"})

    def broken(session: StoredSession) -> FillReport:
        raise FetchError("no browser")

    forms.app.state.form_filler = broken  # type: ignore[attr-defined]
    assert forms.post(f"/api/forms/fills/{sid}/fill").status_code == 422
    assert forms.get(f"/api/forms/fills/{sid}").json()["status"] == "analyzed"


def test_the_session_is_claimed_before_the_browser_opens(forms: TestClient) -> None:
    sid = _start(forms)["id"]
    forms.put(f"/api/forms/fills/{sid}/fields/f2", json={"value": "teal"})
    fill = f"/api/forms/fills/{sid}/fill"
    during: list[int] = []

    def retried(session: StoredSession) -> FillReport:
        during.append(forms.post(fill).status_code)
        return FillReport(("f2",), ())

    forms.app.state.form_filler = retried  # type: ignore[attr-defined]
    assert forms.post(fill).status_code == 200
    assert during == [409]
