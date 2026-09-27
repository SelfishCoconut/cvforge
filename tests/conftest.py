"""Shared fixtures."""

import ipaddress
import json
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai import models as pydantic_ai_models

from cvforge.app import create_app
from cvforge.kb import apply, migrate, queries
from cvforge.kb.db import make_engine
from cvforge.kb.models import ProposalDraft
from cvforge.kb.schema import evidence as evidence_table
from cvforge.kb.schema import metadata
from cvforge.kb.vocab import SourceKind

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback(host: str) -> bool:
    """True for a loopback name or address; false otherwise, including an unresolved name."""
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a hostname we don't special-case: refuse rather than risk a DNS lookup


@pytest.fixture(autouse=True)
def _no_live_traffic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Refuse non-loopback network access and real model requests in every test (NFR-01, NFR-08).

    Without this, a test that reaches for a real socket does not fail fast: the
    address is unroutable in this environment, and the OS falls through to its
    connect timeout (tens of seconds) instead of refusing immediately. Loopback is
    exempted so the `TestClient`'s in-process transport, the in-memory SQLite
    engine and a test that binds its own localhost socket keep working.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _check(sock: socket.socket, address: Any) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) else address
            if not _is_loopback(str(host)):
                raise OSError("non-local network access is disabled in tests (NFR-01/NFR-08)")

    def guarded_connect(sock: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        _check(sock, address)
        return real_connect(sock, address, *args, **kwargs)

    def guarded_connect_ex(sock: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        _check(sock, address)
        return real_connect_ex(sock, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(pydantic_ai_models, "ALLOW_MODEL_REQUESTS", False)
    yield


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


@pytest.fixture(autouse=True)
def _never_open_a_database_outside_tmp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """Fail any test whose app would open a knowledge base outside its own `tmp_path`.

    `create_app` opens `Settings().database_path` when it starts, and the default
    `data_dir` is the real `./data`. A test that forgets to pass its own `data_dir`
    would silently create, migrate and back up the user's real knowledge base.
    """
    real_open = migrate.open_database

    def guarded(path: Path, backup_dir: Path) -> sa.Engine:
        assert path.resolve().is_relative_to(tmp_path.resolve()), (
            f"a test opened {path}, outside its tmp_path; pass Settings(data_dir=tmp_path / 'data')"
        )
        return real_open(path, backup_dir)

    monkeypatch.setattr("cvforge.app.open_database", guarded)
    yield


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
