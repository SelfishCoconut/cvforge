"""Migrations: head matches the declared schema, and nothing migrates without a backup."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.util.exc import CommandError

from cvforge.kb import migrate
from cvforge.kb.db import make_engine
from cvforge.kb.schema import metadata

pytestmark = pytest.mark.integration


def test_migrating_a_fresh_file_reaches_head_without_a_backup(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    engine = open_db(tmp_path / "cvforge.db")
    assert migrate.current_revision(engine) == migrate.head_revision()
    assert not (tmp_path / "backups").exists()


def test_the_migrated_schema_matches_the_declared_one(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    """A schema edit without a migration (or the reverse) fails here, not in production."""
    engine = open_db(tmp_path / "cvforge.db")
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diffs == []


def test_the_migrated_database_enforces_the_check_constraints(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    """compare_metadata does not compare CHECK constraints, so prove one survived."""
    engine = open_db(tmp_path / "cvforge.db")
    now = sa.func.current_timestamp()
    with pytest.raises(sa.exc.IntegrityError, match="ck_entity_state"), engine.begin() as conn:
        conn.execute(
            sa.insert(metadata.tables["entity"]).values(
                kind="skill",
                name="x",
                normalized_name="x",
                state="rusty",
                first_seen_at=now,
                updated_at=now,
            )
        )


def test_reopening_at_head_takes_no_backup(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    db = tmp_path / "cvforge.db"
    open_db(db).dispose()
    engine = open_db(db, migrated=False)
    assert migrate.upgrade(engine, db, tmp_path / "backups") is None


def test_a_pending_migration_backs_the_file_up_first(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    db = tmp_path / "cvforge.db"
    engine = open_db(db)
    with engine.begin() as conn:  # pretend the file predates the head revision
        conn.execute(sa.text("UPDATE alembic_version SET version_num = 'older'"))
        conn.execute(sa.text("CREATE TABLE marker (x INTEGER)"))
    engine.dispose()

    engine = open_db(db, migrated=False)
    with pytest.raises(CommandError, match="older"):  # alembic cannot resolve the fake revision
        migrate.upgrade(engine, db, tmp_path / "backups")
    (copy,) = (tmp_path / "backups").iterdir()
    assert copy.name.startswith("cvforge-older-")
    # The copy was taken BEFORE the failed upgrade, so it still has the marker.
    with open_db(copy, migrated=False).connect() as conn:
        tables = sa.inspect(conn).get_table_names()
    assert "marker" in tables


def _check_constraints(engine: sa.Engine) -> dict[str, str]:
    """Every named CHECK constraint in the database, mapped to its normalised expression."""
    with engine.connect() as conn:
        statements = conn.execute(
            sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL")
        ).scalars()
        ddl = " ".join(re.sub(r"\s+", " ", statement) for statement in statements)
    return dict(re.findall(r"CONSTRAINT (ck_\w+) CHECK \((.*?)\)(?:,| \)| CONSTRAINT)", ddl))


def test_the_migrated_check_constraints_match_the_declared_ones(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    """`compare_metadata` ignores CHECK constraints, and the coverage floor omits migrations.

    That leaves this comparison as the only thing that notices a revision which
    weakens, drops or mistypes a constraint the unit tests (built from `schema.py`)
    would never see.
    """
    declared = make_engine(None)
    metadata.create_all(declared)
    migrated = open_db(tmp_path / "cvforge.db")

    expected = _check_constraints(declared)
    assert len(expected) > 20, "the regex stopped seeing the constraints; fix it, do not relax this"
    assert _check_constraints(migrated) == expected
