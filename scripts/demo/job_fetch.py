"""Demo (FR-17, M3): fetch a job page both ways and see local and bad targets refused.

Offline: a throwaway HTTP server on loopback serves a synthetic posting and a
JavaScript-style empty shell; a stand-in renderer plays the browser. No model, no
internet, nothing written. It exits non-zero if any path misbehaves.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from cvforge.web.fetch import FetchError, fetch_page

_TEXT = " ".join(["We need a backend engineer to build reliable Python data services."] * 6)
PAGES = {
    "/job": f"<html><head><title>Backend Engineer</title></head><body><p>{_TEXT}</p></body></html>",
    "/board": "<html><head><title>Board</title></head><body><div id=root></div></body></html>",
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGES.get(self.path, "").encode())

    def log_message(self, format: str, *args: object) -> None:
        return


class _StandInBrowser:
    def render(self, url: str) -> str:
        return PAGES["/job"]


def main() -> int:
    """Fetch a static page, a script-rendered page, and two refused targets.

    Returns:
        0 when every path behaved as designed, 1 otherwise.
    """
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        static = fetch_page(f"{base}/job", allow_local=True)
        print(f"1. static   {static.method:7} {len(static.text)} chars, title {static.title!r}")
        browser = fetch_page(f"{base}/board", browser=_StandInBrowser(), allow_local=True)
        print(f"2. fallback {browser.method:7} {len(browser.text)} chars")
        refused = []
        for url in (f"{base}/job", "file:///etc/passwd"):
            try:
                fetch_page(url)
            except FetchError as exc:
                refused.append(str(exc))
                print(f"3. refused  {url} -> {exc}")
    finally:
        server.shutdown()
        server.server_close()
    ok = static.method == "static" and browser.method == "browser" and len(refused) == 2
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
