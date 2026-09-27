"""Export the knowledge base to a portable single-file copy (NFR-09).

Usage::

    uv run python -m cvforge.kb.export /path/to/copy.db

The copy is taken with SQLite's online backup API, so it is consistent even while
the app is running, and it opens with any SQLite tool. Its path must be outside
the repository, or under a gitignored directory: the copy is the real knowledge
base.
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from cvforge.config import Settings


def export_database(db_path: Path, destination: Path) -> Path:
    """Copy the database at `db_path` to `destination`.

    Args:
        db_path: The live database file.
        destination: Where to write the copy. It must not exist yet.

    Returns:
        The destination path.

    Raises:
        FileNotFoundError: If there is no database at `db_path`.
        FileExistsError: If `destination` already exists (never overwrite).
    """
    if not db_path.is_file():
        raise FileNotFoundError(f"no knowledge base at {db_path}")
    if destination.exists():
        raise FileExistsError(f"{destination} already exists; refusing to overwrite it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # closing(): a sqlite3 connection's own context manager commits but never closes.
    with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
    return destination


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments; `sys.argv[1:]` when omitted.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Export the CVForge knowledge base.")
    parser.add_argument("destination", type=Path, help="path of the copy to write")
    args = parser.parse_args(argv)
    try:
        written = export_database(Settings().database_path, args.destination)
    except (FileNotFoundError, FileExistsError) as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    print(f"exported to {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
