"""Shared fixtures."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client over a freshly built application with default settings."""
    with TestClient(create_app()) as test_client:
        yield test_client


# --- golden-snapshot harness -------------------------------------------------

SNAPSHOT_DIR = Path(__file__).parent / "golden" / "snapshots"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the snapshot-rewriting flag.

    Args:
        parser: The pytest argument parser.
    """
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite golden snapshots instead of comparing against them.",
    )


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Callable[[str, object], None]:
    """Compare a value against its committed golden snapshot.

    With `--update-golden` the snapshot is rewritten and the test is reported as
    skipped, so an update run can never be mistaken for a passing comparison.

    Args:
        request: The pytest request, used to read the `--update-golden` flag.

    Returns:
        A callable taking the snapshot name and the value to compare.
    """

    def compare(name: str, value: object) -> None:
        path = SNAPSHOT_DIR / f"{name}.json"
        rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if request.config.getoption("--update-golden"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            pytest.skip(f"golden snapshot {name!r} rewritten — review the diff")
        if not path.is_file():
            pytest.fail(
                f"missing golden snapshot {path}. Create it with: "
                f"uv run pytest -m golden --no-cov --update-golden"
            )
        assert rendered == path.read_text(encoding="utf-8"), (
            f"golden snapshot {name!r} no longer matches. If this change is "
            f"intended, run `make update-golden` and justify the diff in the PR."
        )

    return compare
