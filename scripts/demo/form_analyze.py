"""Demo (FR-35, M8): list the fields of an application form served from a local fixture, offline.

A throwaway HTTP server on loopback serves a synthetic form and a page with no form. It exits
non-zero if a labelled field is missed, an unlabelled one is dropped, a hidden or submit control
shows up, or a page without a form raises.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from cvforge.forms.analyze import analyze_form
from cvforge.web.fetch import fetch_html

FORM = """<form>
<label for=n>Full name</label><input id=n name=full_name required>
<label>Email <input type=email name=email></label>
<select name=level aria-label="Level"><option>Junior</option><option>Senior</option></select>
<input>
<input type=hidden name=csrf value=x><input type=submit value=Send>
</form>"""
PAGES = {"/form": FORM, "/none": "<html><body><p>No form here</p></body></html>"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGES.get(self.path, "").encode())

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    """Analyse a form page and a page without a form.

    Returns:
        0 when every field was found and nothing spurious was, 1 otherwise.
    """
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        fields = analyze_form(fetch_html(f"{base}/form", allow_local=True))
        none = analyze_form(fetch_html(f"{base}/none", allow_local=True))
    finally:
        server.shutdown()
        server.server_close()
    for f in fields:
        flag = "required" if f.required else "optional"
        print(f"{f.key:3} {f.type:8} {flag:8} {f.label!r}{'' if f.labelled else '  (no label)'}")
    print(f"page without a form -> {none}")
    labels = [f.label for f in fields]
    ok = labels[:3] == ["Full name", "Email", "Level"] and len(fields) == 4 and none == []
    return 0 if ok and not fields[3].labelled else 1


if __name__ == "__main__":
    raise SystemExit(main())
