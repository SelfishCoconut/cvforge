"""FR-06 / invariant 2: `kb/apply.py` is the only module that writes.

This scans source with the `ast` module rather than a regex: it flags any use of
SQLAlchemy's `insert`, `update` or `delete` constructs, and any string literal
that is DML, in every module under `src/cvforge/` except `kb/apply.py`.
Alembic revisions under `kb/migrations/` are schema changes, not knowledge
writes, and are exempt; a data migration that needs DML there is a design
decision for review, not something this test should quietly allow elsewhere.
"""

import ast
import re
from pathlib import Path

import pytest

from cvforge.kb import apply

SRC = Path(__file__).resolve().parents[2] / "src" / "cvforge"
WRITER = SRC / "kb" / "apply.py"
EXEMPT_DIRS = (SRC / "kb" / "migrations",)
WRITE_CONSTRUCTS = frozenset({"insert", "update", "delete"})
DML = re.compile(r"^\s*(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|REPLACE\s+INTO)\b", re.I)


def writes_in(source: str) -> list[int]:
    """Return the line numbers of every write construct in `source`."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            if any(alias.name in WRITE_CONSTRUCTS for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in WRITE_CONSTRUCTS:
            if isinstance(node.value, ast.Name) and node.value.id in {"sa", "sqlalchemy"}:
                lines.append(node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and DML.search(node.value)
        ):
            lines.append(node.lineno)
    return sorted(lines)


def _modules() -> list[Path]:
    return [
        path
        for path in sorted(SRC.rglob("*.py"))
        if path != WRITER and not any(path.is_relative_to(d) for d in EXEMPT_DIRS)
    ]


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_module_but_apply_writes(path: Path) -> None:
    assert writes_in(path.read_text(encoding="utf-8")) == [], (
        f"{path.relative_to(SRC)} constructs a database write. Invariant 2: only "
        "kb/apply.py may write. Move the mutation there."
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "from sqlalchemy import insert",
        "import sqlalchemy as sa\nsa.update(t)",
        "import sqlalchemy\nsqlalchemy.delete(t)",
        "q = 'INSERT INTO entity VALUES (1)'",
        "conn.exec_driver_sql('delete from edge')",
        "x = '''\n  UPDATE assertion SET field = 1'''",
    ],
)
def test_the_scanner_catches_every_write_idiom(snippet: str) -> None:
    """A scanner that silently matches nothing reads as a pass; hold it to cases."""
    assert writes_in(snippet) != []


@pytest.mark.parametrize(
    "snippet",
    [
        "import sqlalchemy as sa\nsa.select(t)",
        "items.update(x)",
        "s = 'update the docs'",
        "d.delete()",
    ],
)
def test_the_scanner_ignores_reads_and_unrelated_calls(snippet: str) -> None:
    assert writes_in(snippet) == []


def test_the_writer_itself_is_scanned_positive() -> None:
    """If this fails, the scanner is broken, not the invariant."""
    assert writes_in(WRITER.read_text(encoding="utf-8"))


def test_apply_public_surface_is_exactly_the_reviewed_entry_points() -> None:
    """A new public writer must be a deliberate, reviewed change to this list."""
    public = {
        name
        for name, value in vars(apply).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", "") == apply.__name__
        and not isinstance(value, type)
    }
    assert public == {
        "record_source",
        "record_evidence",
        "record_proposal",
        "review_operation",
        "commit_proposal",
    }
