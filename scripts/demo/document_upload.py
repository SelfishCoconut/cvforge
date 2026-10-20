"""Demo (FR-14, M2): upload a document, see its extracted text, and see nothing reach the knowledge.

Offline: a synthetic Markdown file is built in memory and stored in a throwaway directory, so no
model, no network and nothing under the real `data/`. It exits non-zero if the upload
wrote any entity, edge or assertion, or if an unsupported file was accepted.
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import queries
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata


def main() -> int:
    """Upload a Markdown file, then an unsupported file, and report what was stored.

    Returns:
        0 when the flow behaved as designed, 1 otherwise.
    """
    engine = make_engine(None)
    metadata.create_all(engine)
    with tempfile.TemporaryDirectory() as scratch:
        settings = Settings(data_dir=Path(scratch) / "data", frontend_dist=Path(scratch) / "none")
        app = create_app(settings, engine=engine)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            data = b"# Experience\n\nBackend engineer at Acme. Skills: Python and Rust.\n"
            ok = client.post("/api/documents", files={"file": ("cv.md", data)})
            print(f"1. uploaded  cv.md -> {ok.status_code} {ok.json()}")
            bad = client.post("/api/documents", files={"file": ("setup.exe", b"MZ")})
            print(f"2. refused   setup.exe -> {bad.status_code} {bad.json()['detail']}")
        stored = sorted(p.name for p in (Path(scratch) / "data" / "documents").iterdir())
        print(f"3. stored    {len(stored)} files under data/documents/")
    with engine.connect() as conn:
        counts = queries.table_counts(conn)
    print(f"4. knowledge source={counts['source']} entity={counts['entity']} edge={counts['edge']}")
    clean = counts["entity"] == counts["edge"] == counts["assertion"] == 0
    return 0 if ok.status_code == 201 and bad.status_code == 415 and clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
