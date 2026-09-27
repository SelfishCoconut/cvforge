"""Generate an Alembic revision from the difference between `kb/schema.py` and head.

Usage::

    make migration MSG="add seniority to skill"

It migrates a throwaway database in a temporary directory to head, then asks
Alembic to autogenerate the difference against `schema.py`. The real
`data/cvforge.db` is never opened. READ THE GENERATED FILE: autogenerate misses
some changes (CHECK constraint edits, renames), and a destructive step needs an
export first (kb-schema skill).
"""

import sys
import tempfile
from pathlib import Path

from alembic import command

from cvforge.kb import migrate


def main(argv: list[str]) -> int:
    """Create the revision file.

    Args:
        argv: A single argument, the revision message.

    Returns:
        Process exit code.
    """
    if len(argv) != 1 or not argv[0].strip():
        print('usage: new_migration.py "short description"', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as scratch:
        db = Path(scratch) / "head.db"
        engine = migrate.open_database(db, Path(scratch) / "backups")
        next_id = f"{int(migrate.head_revision()) + 1:04d}"
        config = migrate.alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.revision(config, message=argv[0], autogenerate=True, rev_id=next_id)
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
