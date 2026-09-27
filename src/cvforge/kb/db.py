"""Engine construction for the single-file knowledge base (ADR-0001, NFR-09)."""

import sqlite3
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
