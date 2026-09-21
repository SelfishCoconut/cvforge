"""Shared fixtures."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.kb import apply, migrate, queries
from cvforge.kb.db import make_engine
from cvforge.kb.models import ProposalDraft
from cvforge.kb.schema import evidence as evidence_table
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind


@pytest.fixture
def kb() -> Iterator[sa.Engine]:
    """A fresh, empty in-memory knowledge base with the full schema (no disk I/O)."""
    engine = make_engine(None)
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def evidence_id(kb: sa.Engine) -> int:
    """One synthetic conversation message, recorded as a source plus evidence."""
    source = apply.record_source(kb, SourceKind.CONVERSATION, "synthetic chat")
    return apply.record_evidence(kb, source, "message:1", "I built a parser in Rust at Acme.")


@pytest.fixture
def client(kb: sa.Engine) -> Iterator[TestClient]:
    """A test client over a freshly built application backed by the in-memory `kb`."""
    with TestClient(create_app(engine=kb)) as test_client:
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


# --- knowledge-base builders -------------------------------------------------

Propose = Callable[..., int]


@pytest.fixture
def propose(kb: sa.Engine, evidence_id: int) -> Propose:
    """Record a chat proposal from bare payload dicts; returns the proposal id.

    Each positional argument is a payload dict (`evidence_id` is filled in when
    absent) or an `(payload, classification, target_kind, target_id)` tuple for a
    non-`new` operation. With `accept=True` every operation is accepted.
    """

    def build(*ops: object, accept: bool = False) -> int:
        operations = []
        for seq, op in enumerate(ops):
            payload, classification, target_kind, target_id = (
                op if isinstance(op, tuple) else (op, "new", None, None)
            )
            operations.append(
                {
                    "seq": seq,
                    "payload": {"evidence_id": evidence_id, **payload},
                    "classification": classification,
                    "target_kind": target_kind,
                    "target_id": target_id,
                }
            )
        source_id = _source_of(kb, evidence_id)
        draft = ProposalDraft.model_validate(
            {"origin": "chat", "source_id": source_id, "summary": "test", "operations": operations}
        )
        proposal_id = apply.record_proposal(kb, draft)
        if accept:
            _accept_all(kb, proposal_id)
        return proposal_id

    return build


def _source_of(engine: sa.Engine, evidence: int) -> int:
    with engine.connect() as conn:
        query = sa.select(evidence_table.c.source_id).where(evidence_table.c.id == evidence)
        return int(conn.execute(query).scalar_one())


def _accept_all(engine: sa.Engine, proposal_id: int) -> None:
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    assert record is not None
    for op in record.operations:
        apply.review_operation(engine, op.id, "accept")


OpenDb = Callable[..., sa.Engine]


@pytest.fixture
def open_db() -> Iterator[OpenDb]:
    """Open file-backed databases, and dispose every one of them at teardown.

    `open_db(path)` migrates to head (backups go next to the file, under
    `backups/`); `open_db(path, migrated=False)` only builds the engine.
    """
    opened: list[sa.Engine] = []

    def factory(path: Path, *, migrated: bool = True) -> sa.Engine:
        engine = (
            migrate.open_database(path, path.parent / "backups") if migrated else make_engine(path)
        )
        opened.append(engine)
        return engine

    yield factory
    for engine in opened:
        engine.dispose()
