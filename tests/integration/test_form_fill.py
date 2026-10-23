"""FR-37: a fill run writes only confirmed fields in a real browser and never submits."""

import sys
import threading
from collections.abc import Iterator
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from cvforge.forms.fill import FillReport, _fill_page, fill_session
from cvforge.forms.store import StoredSession
from cvforge.kb.vocab import FillStatus
from cvforge.web.fetch import FetchError

pytestmark = pytest.mark.integration

FORM = """<html><body>
<form action="/submit" method="post" onsubmit="fetch('/submitted')">
<label for=y>Years</label><input id=y name=y>
<label for=n>Notes</label><textarea id=n name=n>keep me</textarea>
<label for=l>Level</label><select id=l name=l>
<option value=jr>jr</option><option value=sr>sr</option></select>
<label for=ok>Relocate</label><input type=checkbox id=ok name=ok>
<label>Remote <input type=radio name=r value=yes></label>
<label>Hybrid <input type=radio name=r value=no></label>
<label for=p>Password</label><input type=password id=p name=p>
<input type=submit id=go value=Apply onclick="fetch('/clicked')">
</form></body></html>"""
NONAME = "<form><label>Solo <input type=radio value=a></label></form>"
SUBRESOURCE = '<form><label for=y>Years</label><input id=y><img src="/blocked/pixel"></form>'
HITS: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        HITS.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/blocked/redirected")
            self.end_headers()
            return
        body = {"/form": FORM, "/noname": NONAME, "/subresource": SUBRESOURCE}.get(self.path, "")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def form_url() -> Iterator[str]:
    HITS.clear()
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/form"
    server.shutdown()


def _entry(key: str, label: str, kind: str, value: str | None, **extra: Any) -> dict[str, Any]:
    return {
        "key": key, "label": label, "type": kind, "required": False, "options": [],
        "selector": "", "suggested": value, "claim_ids": [], "reason": "",
        "confirmed_value": value, "confirmed": value is not None, **extra,
    }  # fmt: skip


def _session(url: str, entries: list[dict[str, Any]]) -> StoredSession:
    return StoredSession(1, None, 1, url, entries, FillStatus.ANALYZED, datetime(2026, 1, 1))


def _run(url: str, entries: list[dict[str, Any]], tmp_path: Path) -> FillReport:
    return fill_session(
        _session(url, entries), tmp_path / "profile", headless=True, allow_local=True
    )


def test_only_confirmed_fields_are_written_and_the_form_is_never_submitted(
    form_url: str, tmp_path: Path
) -> None:
    entries = [
        _entry("f1", "Years", "text", "7"),
        _entry("f2", "Notes", "textarea", None),
        _entry("f3", "Level", "select", "sr", options=["jr", "sr"]),
        _entry("f4", "Relocate", "checkbox", "yes"),
        _entry("f5", "Remote", "radio", "no", options=["yes", "no"]),
        _entry("f6", "Password", "password", "hunter2"),
    ]

    report = _run(form_url, entries, tmp_path)

    assert report.filled == ("f1", "f3", "f4", "f5")
    assert report.skipped == (("f6", "a password is never filled"),)
    assert [h for h in HITS if h != "/form"] == []


def test_a_field_whose_label_changed_is_skipped(form_url: str, tmp_path: Path) -> None:
    report = _run(form_url, [_entry("f1", "Salary", "text", "1")], tmp_path)
    assert report.filled == () and "changed" in report.skipped[0][1]


def test_a_field_gone_from_the_page_is_skipped(form_url: str, tmp_path: Path) -> None:
    report = _run(form_url, [_entry("f99", "Years", "text", "1")], tmp_path)
    assert report.skipped == (("f99", "the field is no longer on the page"),)


def test_an_unnamed_radio_group_is_skipped(form_url: str, tmp_path: Path) -> None:
    report = _run(
        form_url.replace("/form", "/noname"), [_entry("f1", "Solo", "radio", "a")], tmp_path
    )
    assert report.filled == () and "unnamed" in report.skipped[0][1]


def test_the_page_holds_exactly_the_confirmed_values(form_url: str) -> None:
    from playwright.sync_api import sync_playwright

    entries = [
        _entry("f1", "Years", "text", "7"),
        _entry("f2", "Notes", "textarea", None),
        _entry("f3", "Level", "select", "sr", options=["jr", "sr"]),
        _entry("f4", "Relocate", "checkbox", "yes"),
        _entry("f5", "Remote", "radio", "no", options=["yes", "no"]),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(form_url)
        _fill_page(page, _session(form_url, entries))
        state = page.evaluate(
            """() => ({y: y.value, n: n.value, l: l.value, ok: ok.checked,
              r: [...document.querySelectorAll('[name=r]')].map(e => e.checked)})"""
        )
        browser.close()
    assert state == {"y": "7", "n": "keep me", "l": "sr", "ok": True, "r": [False, True]}


def test_a_refused_url_never_opens_a_browser(tmp_path: Path) -> None:
    with pytest.raises(FetchError):
        fill_session(_session("http://127.0.0.1:1/x", []), tmp_path / "p", headless=True)
    assert not (tmp_path / "p").exists()


def test_an_unreachable_page_is_a_fetch_error(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="could not fill"):
        _run("http://127.0.0.1:9/form", [], tmp_path)


def test_a_missing_playwright_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(FetchError, match="playwright install"):
        _run("http://127.0.0.1:9/form", [], tmp_path)


@pytest.fixture
def refuse_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the host screen: refuse any URL under /blocked, allow the rest."""
    from cvforge.web import fetch

    real = fetch.check_url

    def check(url: str, *, allow_local: bool = False) -> None:
        if "/blocked" in url:
            raise FetchError("refused")
        real(url, allow_local=True)

    monkeypatch.setattr("cvforge.forms.fill.check_url", check)


def test_a_sub_resource_the_screen_refuses_is_never_requested(
    form_url: str, refuse_blocked: None, tmp_path: Path
) -> None:
    _run(form_url.replace("/form", "/subresource"), [], tmp_path)
    assert not any(h.startswith("/blocked") for h in HITS)


def test_a_redirect_to_a_refused_target_is_never_followed(
    form_url: str, refuse_blocked: None, tmp_path: Path
) -> None:
    with pytest.raises(FetchError):
        _run(form_url.replace("/form", "/redirect"), [], tmp_path)
    assert not any(h.startswith("/blocked") for h in HITS)
