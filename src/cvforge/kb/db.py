"""Engine construction for the single-file knowledge base (ADR-0001, NFR-09)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import sqlite_vec
from sqlalchemy.pool import StaticPool

DATABASE_FILE = "cvforge.db"


def _load_vec_extension(dbapi_connection: sqlite3.Connection) -> None:
    """Load sqlite-vec, so `kb.embeddings`'s `vec0` similarity index is usable.

    Args:
        dbapi_connection: The raw sqlite3 connection being opened.
    """
    dbapi_connection.enable_load_extension(True)
    sqlite_vec.load(dbapi_connection)
    dbapi_connection.enable_load_extension(False)


def _on_connect(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
    """Enforce foreign keys and load sqlite-vec on every connection.

    SQLite ships with foreign keys OFF per connection. Without this pragma an
    evidence row could point at a source that does not exist (FR-12).

    Args:
        dbapi_connection: The raw sqlite3 connection being opened.
        _record: SQLAlchemy's connection record (unused).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()
    _load_vec_extension(dbapi_connection)


def make_engine(path: Path | None) -> sa.Engine:
    """Build the engine for the knowledge base stored at `path`.

    The default rollback journal is kept on purpose: WAL mode would add `-wal`
    and `-shm` files next to the database, and NFR-09 requires one file.

    Args:
        path: The SQLite database file, whose parent directory is created if
            missing. None gives a private in-memory database on a single shared
            connection, which is what unit tests use (no disk I/O).

    Returns:
        An engine with foreign-key enforcement on every connection.
    """
    if path is None:
        engine = sa.create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = sa.create_engine(f"sqlite:///{path}")
    sa.event.listen(engine, "connect", _on_connect)
    return engine


def utc_now() -> datetime:
    """The current UTC time as a naive datetime, the form every timestamp column stores."""
    return datetime.now(UTC).replace(tzinfo=None)


@contextmanager
def write_transaction(engine: sa.Engine) -> Iterator[sa.Connection]:
    """Open a transaction that holds SQLite's write lock before anything is read.

    pysqlite begins a transaction lazily, just before the first INSERT, UPDATE or
    DELETE. A plain `engine.begin()` therefore runs its checks (is the proposal
    still open? which operations are pending?) outside any lock and then writes
    on what it read, so two requests can pass the same check and both write: a
    proposal committed twice, or a reject landing after the commit it should have
    prevented. `BEGIN IMMEDIATE` takes the lock first. The second request waits,
    then reads the state the first one left behind.

    Args:
        engine: The knowledge-base engine.

    Yields:
        A connection inside the transaction. It is committed when the block ends
        and rolled back if the block raises.
    """
    with engine.connect() as conn:
        conn.execute(sa.text("BEGIN IMMEDIATE"))
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
