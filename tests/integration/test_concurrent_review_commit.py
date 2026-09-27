"""FR-09/FR-10 under concurrency: review and commit are serialised.

A decision must never land between a commit's checks and its writes. Both races
are forced deterministically. A `before_cursor_execute` hook holds one thread at
the exact statement where an unserialised implementation is exposed while the
other runs to completion, so these tests do not depend on lucky timing. The hold
is bounded by `HOLD_SECONDS`: an implementation that serialises correctly is
delayed by it, never deadlocked.
"""

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.kb import apply, queries, schema
from cvforge.kb.models import ProposalDraft
from cvforge.kb.vocab import SourceKind

pytestmark = pytest.mark.integration

HOLD_SECONDS = 1.0


@pytest.fixture
def db(tmp_path: Path, open_db: Callable[..., sa.Engine]) -> sa.Engine:
    return open_db(tmp_path / "cvforge.db")


def _open_proposal(engine: sa.Engine) -> tuple[int, int]:
    """One open proposal holding a single `create_entity Rust`; returns (proposal, operation)."""
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "I use Rust.")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "synthetic",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "op_type": "create_entity",
                        "kind": "skill",
                        "name": "Rust",
                        "evidence_id": evidence,
                    },
                    "classification": "new",
                }
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    return proposal, record.operations[0].id


def _run_in_threads(*calls: Callable[[], object]) -> list[BaseException | None]:
    """Run every call in its own thread; return each one's exception, or None."""
    outcomes: list[BaseException | None] = [None] * len(calls)

    def run(index: int, call: Callable[[], object]) -> None:
        try:
            call()
        except BaseException as error:
            outcomes[index] = error

    threads = [threading.Thread(target=run, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads), "a thread hung"
    return outcomes


def _statement_hook(
    engine: sa.Engine, starts_with: str, hold: Callable[[], None], *, thread: str | None = None
) -> None:
    """Call `hold` once, in `thread` (any when None), just before a matching statement runs."""
    fired = threading.Event()

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _hook(
        conn: sa.Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().startswith(starts_with) and (
            thread is None or threading.current_thread().name == thread
        ):
            if not fired.is_set():
                fired.set()
                hold()


def test_two_concurrent_commits_apply_the_proposal_exactly_once(db: sa.Engine) -> None:
    proposal, operation = _open_proposal(db)
    apply.review_operation(db, operation, "accept")

    # Hold each committer at the read of its operations until both have arrived,
    # so an unserialised implementation has passed its "is it open?" check twice.
    barrier = threading.Barrier(2)
    seen = threading.local()

    def wait_for_the_other() -> None:
        try:
            barrier.wait(HOLD_SECONDS)
        except threading.BrokenBarrierError:
            pass  # the other thread was correctly kept out; carry on

    @sa.event.listens_for(db, "before_cursor_execute")
    def _hold(
        conn: sa.Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if "FROM operation" in statement and not getattr(seen, "held", False):
            seen.held = True
            wait_for_the_other()

    outcomes = _run_in_threads(
        lambda: apply.commit_proposal(db, proposal), lambda: apply.commit_proposal(db, proposal)
    )

    assert sum(outcome is None for outcome in outcomes) == 1, outcomes
    assert [o for o in outcomes if o is not None] and all(
        isinstance(o, apply.ProposalNotOpenError) for o in outcomes if o is not None
    ), outcomes
    with db.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 1
        log_rows = conn.execute(sa.select(sa.func.count()).select_from(schema.commit_log)).scalar()
    assert log_rows == 1


def test_a_reject_racing_a_commit_never_leaves_a_rejected_fact_committed(db: sa.Engine) -> None:
    proposal, operation = _open_proposal(db)
    apply.review_operation(db, operation, "accept")

    reached_the_write = threading.Event()
    commit_finished = threading.Event()

    def hold_the_reject() -> None:
        reached_the_write.set()
        commit_finished.wait(HOLD_SECONDS)

    # The reviewer changes their mind: the reject has passed its checks and is about
    # to write when another request commits the proposal.
    _statement_hook(db, "UPDATE operation", hold_the_reject, thread="reject")
    reject = threading.Thread(
        target=lambda: apply.review_operation(db, operation, "reject"), name="reject"
    )
    reject.start()
    assert reached_the_write.wait(10), "the reject never reached its write"
    try:
        apply.commit_proposal(db, proposal)
    finally:
        commit_finished.set()
        reject.join(timeout=30)
    assert not reject.is_alive()

    with db.connect() as conn:
        record = queries.get_proposal(conn, proposal)
        entities = queries.table_counts(conn)["entity"]
    assert record is not None
    status = record.operations[0].status
    # Whichever request won, the outcome is consistent: a fact exists if and only if
    # its operation was applied. A rejected operation must never have produced one.
    assert status in {"rejected", "applied"}, status
    assert entities == (1 if status == "applied" else 0)


def test_a_busy_database_is_a_503_that_writes_nothing_and_can_be_retried(db: sa.Engine) -> None:
    proposal, operation = _open_proposal(db)
    apply.review_operation(db, operation, "accept")

    # New connections give up quickly instead of waiting out the 5 s default.
    db.dispose()

    @sa.event.listens_for(db, "connect")
    def _short_busy_timeout(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        dbapi_connection.execute("PRAGMA busy_timeout = 50")

    holder = db.connect()
    holder.exec_driver_sql("BEGIN IMMEDIATE")  # another writer is mid-transaction
    try:
        with TestClient(create_app(engine=db), base_url="http://127.0.0.1") as client:
            busy = client.post(f"/api/proposals/{proposal}/commit")
    finally:
        holder.rollback()
        holder.close()

    assert busy.status_code == 503
    assert busy.headers["Retry-After"] == "1"
    assert "nothing was written" in busy.json()["detail"]
    with db.connect() as conn:
        assert queries.table_counts(conn)["entity"] == 0
    # The proposal is still open, so the retry the response asks for succeeds.
    with TestClient(create_app(engine=db), base_url="http://127.0.0.1") as client:
        assert client.post(f"/api/proposals/{proposal}/commit").status_code == 200
