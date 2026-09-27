"""Bring the database schema to the latest revision, backing it up first (ADR-0006).

The real knowledge base is the only copy of its data and is not in version
control, so applying a migration without a backup is a bug. `upgrade` copies the
file with SQLite's online backup API before touching the schema, and only when
there is something to apply.
"""

from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from cvforge.kb.db import make_engine
from cvforge.kb.export import export_database

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    """Return the Alembic configuration for `kb/migrations`, with no ini file.

    Returns:
        The configuration; callers put a connection in `attributes["connection"]`.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def head_revision() -> str:
    """Return the newest revision id shipped with this code.

    Returns:
        The head revision of `kb/migrations/versions`.
    """
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("kb/migrations/versions has no revisions")
    return head


def current_revision(engine: sa.Engine) -> str | None:
    """Return the revision the database is at, or None for an unmigrated file.

    Args:
        engine: The knowledge-base engine.

    Returns:
        The stored revision id, or None.
    """
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def backup(db_path: Path, backup_dir: Path, label: str) -> Path:
    """Copy the database file with SQLite's online backup API.

    Args:
        db_path: The live database file.
        backup_dir: Directory the copy is written to; created if missing.
        label: Short tag included in the file name (e.g. the revision).

    Returns:
        The path of the copy.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return export_database(db_path, backup_dir / f"cvforge-{label}-{stamp}.db")


def upgrade(engine: sa.Engine, db_path: Path, backup_dir: Path) -> Path | None:
    """Migrate the database to head, backing up first if it holds a schema.

    Args:
        engine: The knowledge-base engine.
        db_path: The database file behind `engine`.
        backup_dir: Where the pre-migration copy goes.

    Returns:
        The backup path, or None when nothing was backed up (fresh file, or
        already at head).
    """
    current = current_revision(engine)
    if current == head_revision():
        return None
    copy = backup(db_path, backup_dir, current) if current is not None else None
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return copy


def open_database(db_path: Path, backup_dir: Path) -> sa.Engine:
    """Open the knowledge base at `db_path`, migrated to head.

    Args:
        db_path: The database file; created if missing.
        backup_dir: Where a pre-migration copy goes when a migration is pending.

    Returns:
        A ready engine.
    """
    engine = make_engine(db_path)
    upgrade(engine, db_path, backup_dir)
    return engine
