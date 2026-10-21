"""FR-17: both fetch paths against a real HTTP server on loopback, no live internet."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cvforge.web.fetch import FetchError, fetch_page

pytestmark = pytest.mark.integration

_BODY = " ".join(
    ["We need a backend engineer who ships reliable Python services for data pipelines."] * 6
)
PAGES = {
    "/static": f"<html><head><title>Static job</title></head><body><p>{_BODY}</p></body></html>",
    "/shell": "<html><head><title>Shell</title></head><body><div id=root></div></body></html>",
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write((body or "missing").encode())

    def log_message(self, format: str, *args: object) -> None:
        return


class _Renderer:
    def render(self, url: str) -> str:
        return PAGES["/static"]


@pytest.fixture
def base_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_static_path_over_a_real_socket(base_url: str) -> None:
    page = fetch_page(f"{base_url}/static", allow_local=True)
    assert page.method == "static"
    assert "reliable Python services" in page.text


def test_browser_fallback_over_a_real_socket(base_url: str) -> None:
    page = fetch_page(f"{base_url}/shell", browser=_Renderer(), allow_local=True)
    assert page.method == "browser"


def test_local_hosts_are_refused_by_default(base_url: str) -> None:
    with pytest.raises(FetchError, match="local address"):
        fetch_page(f"{base_url}/static")


def test_a_missing_page_is_a_handled_error(base_url: str) -> None:
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_page(f"{base_url}/nope", allow_local=True)
