"""Demo (FR-36, FR-37, M8): suggest values from a CV, fill only the confirmed ones, never submit.

A throwaway loopback server serves a synthetic form whose submit button reports any click or
submission. A hand-built CV supplies the suggestions; two fields are confirmed, one is left
alone. It exits non-zero if a suggestion is invented, an unconfirmed field is written, or
anything beyond the page itself was requested (a submit). Needs `uv sync --extra browser` and
`playwright install chromium`; it skips cleanly (exit 0) when Playwright is absent.
"""

import tempfile
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from cvforge.cv.store import StoredClaim, StoredCv
from cvforge.forms.analyze import analyze_form
from cvforge.forms.fill import fill_session
from cvforge.forms.options import suggest_values
from cvforge.forms.store import StoredSession
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, CvStatus, FillStatus, GenerationMode
from cvforge.web.fetch import FetchError

FORM = """<form action="/submit" method="post">
<label for=y>Years of experience</label><input id=y name=y>
<label for=c>Favourite colour</label><input id=c name=c>
<label for=s>Key skills</label><input id=s name=s>
<input type=submit value=Apply onclick="fetch('/clicked')">
</form>"""
PERIOD = "2019-01 to 2024-01"
HITS: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        HITS.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(FORM.encode() if self.path == "/form" else b"")

    def do_POST(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


def _cv() -> StoredCv:
    claims = (
        StoredClaim(1, "Experience", 0, ClaimSlot.PERIOD, 0, ClaimBasis.PERIOD, PERIOD, 1, 1, None),
        StoredClaim(2, "Skills", 0, ClaimSlot.BULLET, 0, ClaimBasis.NAME, "Python", 2, 2, None),
    )  # fmt: skip
    return StoredCv(
        1, 1, 1, None, None, GenerationMode.AUTOMATIC, CvStatus.DRAFT, datetime(2026, 1, 1),
        None, None, None, claims,
    )  # fmt: skip


def main() -> int:
    """Run the suggest, confirm, fill cycle against the fixture form.

    Returns:
        0 when only confirmed fields were filled and nothing was submitted, 1 otherwise.
    """
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/form"
    try:
        fields = analyze_form(FORM)
        suggestions = suggest_values(fields, _cv(), date(2026, 10, 21))
        for f, s in zip(fields, suggestions, strict=True):
            print(f"{f.label!r:26} -> {s.value!r}  ({s.reason})")
        entries = [
            {"key": f.key, "label": f.label, "type": f.type, "confirmed": f.key != "f3",
             "confirmed_value": s.value, "selector": f.selector}
            for f, s in zip(fields, suggestions, strict=True) if s.value is not None
        ]  # fmt: skip
        session = StoredSession(1, None, 1, url, entries, FillStatus.ANALYZED, datetime.now())
        with tempfile.TemporaryDirectory() as profile:
            report = fill_session(session, Path(profile), headless=True, allow_local=True)
    except FetchError as exc:
        print(f"skipped: {exc}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
    print(f"filled {report.filled}, requested {HITS}")
    invented = [s for f, s in zip(fields, suggestions, strict=True) if f.key == "f2" and s.value]
    ok = report.filled == ("f1",) and not invented and HITS == ["/form"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
