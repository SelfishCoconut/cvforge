"""FR-35: form analysis against local fixture pages, static and JavaScript-built (real Chromium)."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cvforge.forms.analyze import analyze_form
from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import fetch_html

pytestmark = pytest.mark.integration

STATIC = "<form><label for=n>Full name</label><input id=n name=full_name required></form>"
SHELL = """<html><body><div id=root></div><script>
document.getElementById('root').innerHTML =
  '<form><label for="e">Email</label><input id="e" type="email" required></form>';
</script></body></html>"""
PAGES = {"/static": STATIC, "/js": SHELL, "/none": "<html><body><p>No form here</p></body></html>"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = PAGES.get(self.path, "")
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def base_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def _fields(url: str) -> list[tuple[str, str, bool]]:
    html = fetch_html(url, browser=PlaywrightFetcher(allow_local=True), allow_local=True)
    return [(f.label, f.type, f.required) for f in analyze_form(html)]


def test_a_static_form_is_analysed(base_url: str) -> None:
    assert _fields(f"{base_url}/static") == [("Full name", "text", True)]


def test_a_javascript_built_form_is_analysed_through_the_browser(base_url: str) -> None:
    assert _fields(f"{base_url}/js") == [("Email", "email", True)]


def test_a_page_without_a_form_gives_an_empty_list(base_url: str) -> None:
    assert _fields(f"{base_url}/none") == []
