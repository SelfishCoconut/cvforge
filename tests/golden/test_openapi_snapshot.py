"""The published API contract, pinned to a committed snapshot.

Any route added, removed or reshaped changes this snapshot. That is the point:
`pytest -m golden --update-golden` regenerates it, and reviewing the resulting
diff is the gate.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.golden


def test_openapi_schema_matches_snapshot(
    client: TestClient, golden: Callable[[str, object], None]
) -> None:
    schema = client.get("/openapi.json").json()
    # The version travels with the package, so a release bump would otherwise
    # churn the snapshot for no behavioural reason.
    schema["info"].pop("version", None)
    golden("openapi", schema)
