"""Demo (infra): prove the walking skeleton answers /api/health, fully offline.

Uses the in-process test client rather than a real server so the demo needs no
port, no build and no network — exactly what CI's `demos` job requires.
"""

import json

from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata


def main() -> int:
    """Call /api/health through the in-process client and print the result.

    Returns:
        0 when the endpoint answered 200, 1 otherwise.
    """
    engine = make_engine(None)  # in-memory: a demo must never touch data/cvforge.db
    metadata.create_all(engine)
    with TestClient(create_app(engine=engine)) as client:
        response = client.get("/api/health")
    print(f"GET /api/health -> {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
