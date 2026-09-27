"""FR-06 / invariant 2: `kb/apply.py` is the only module that writes.

This scans source with the `ast` module rather than a regex. In every module under
`src/cvforge/` except `kb/apply.py` it flags:

- SQLAlchemy's `insert`, `update` and `delete`, imported, called as `sa.insert(...)`,
  or called in method form on a chain rooted at `sa`, `sqlalchemy` or `schema`
  (`schema.entity.insert()`, `sa.sql.insert(t)`);
- the driver-level escape hatches `exec_driver_sql`, `executescript` and
  `executemany`, which bypass the constructs above;
- any string literal containing DML, wherever in the string it sits (a leading
  comment, `BEGIN;`, `WITH ... INSERT`, `INSERT OR REPLACE`, a quoted or
  schema-qualified table name);
- `import sqlite3`, outside the two modules that legitimately use the driver.

Alembic revisions under `kb/migrations/` are schema changes, not knowledge
writes, and are exempt (ADR-0010); a data migration that needs DML there is a
design decision for review, not something this test should quietly allow elsewhere.

Known limits: a write through a variable that merely holds a table
(`t = schema.entity; t.insert()`), or a table imported by name
(`from cvforge.kb.schema import entity`), is not visible to a syntax scan —
neither the general write-construct scan nor `references_knowledge_table`
below resolves it. Nor is SQL assembled at runtime (`'INS' + 'ERT INTO'`).
Docstrings are not scanned, so prose can mention SQL. The `kb-write-path` hook
and the `provenance-auditor` agent are the second net.

A module may also be **registered** as a writer of specific non-knowledge
tables (ADR-0011): it is exempt from the scan above (it is allowed to write),
but never from referencing a knowledge table it wasn't registered for.
`REGISTERED_WRITERS` starts empty; `llm/settings_store.py` joins it in M1b task
B1.3, `kb/embeddings.py` in B2. Editing it is a deliberate, reviewed line, not
a side effect of adding a module.
"""

import ast
import re
from pathlib import Path

import pytest

from cvforge.kb import apply, schema

SRC = Path(__file__).resolve().parents[2] / "src" / "cvforge"
WRITER = SRC / "kb" / "apply.py"
EXEMPT_DIRS = (SRC / "kb" / "migrations",)
SQLITE3_MODULES = (SRC / "kb" / "db.py", SRC / "kb" / "export.py")
REGISTERED_WRITERS: dict[str, frozenset[str]] = {
    "llm/settings_store.py": frozenset({"app_setting"}),
}
KNOWLEDGE_TABLES = frozenset(schema.metadata.tables) - frozenset().union(
    *REGISTERED_WRITERS.values()
)
WRITE_CONSTRUCTS = frozenset({"insert", "update", "delete"})
DRIVER_ESCAPES = frozenset({"exec_driver_sql", "executescript", "executemany"})
SQLALCHEMY_ROOTS = frozenset({"sa", "sqlalchemy", "schema"})
DML = re.compile(
    # A statement starts at the beginning of the string, or after `;`, a newline, a
    # closing parenthesis (a CTE) or a block comment. Anchoring keeps prose such as
    # "we insert into the plan" from reading as SQL.
    r"(?:^|[;\n)]|\*/)\s*"
    r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO"
    r"|REPLACE\s+INTO"
    r"|DELETE\s+FROM"
    r"|UPDATE\s+(?:OR\s+\w+\s+)?[\"`\[\w.]+\s+SET)\b",
    re.I,
)


def _root(node: ast.expr) -> str | None:
    """The name an attribute chain starts from: `schema` for `schema.entity.insert`."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of every docstring constant, so prose is never scanned as SQL."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def writes_in(source: str) -> list[int]:
    """Return the line numbers of every write construct in `source`."""
    lines: list[int] = []
    tree = ast.parse(source)
    prose = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            if any(alias.name in WRITE_CONSTRUCTS for alias in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.Attribute):
            if node.attr in DRIVER_ESCAPES or (
                node.attr in WRITE_CONSTRUCTS and _root(node.value) in SQLALCHEMY_ROOTS
            ):
                lines.append(node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in prose
            and DML.search(node.value)
        ):
            lines.append(node.lineno)
    return sorted(lines)


def imports_sqlite3(source: str) -> bool:
    """True if `source` imports the stdlib `sqlite3` driver."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] == "sqlite3" for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlite3":
            return True
    return False


def _all_non_exempt_modules() -> list[Path]:
    """Every module under `src/cvforge/` except `apply.py` and the migrations directory.

    Unlike `_modules()`, this does NOT exempt registered writers: the
    sqlite3-import bar (ADR-0011) applies to them too, unless a registry entry
    explicitly says a writer needs the raw driver — none does today.
    """
    return [
        path
        for path in sorted(SRC.rglob("*.py"))
        if path != WRITER and not any(path.is_relative_to(d) for d in EXEMPT_DIRS)
    ]


def _modules() -> list[Path]:
    """Modules subject to the "no write outside `apply.py`" scan; registered writers are exempt."""
    return [
        path
        for path in _all_non_exempt_modules()
        if str(path.relative_to(SRC)) not in REGISTERED_WRITERS
    ]


def references_knowledge_table(source: str, allowed: frozenset[str]) -> bool:
    """True if `source` references any knowledge table `allowed` doesn't cover.

    Looks for `schema.<table>` attribute access and for the bare table name
    inside a string literal, so a registered writer building SQL with `sa.text`
    is caught the same way a knowledge writer would be. Docstrings are excluded
    (as in `writes_in`), so a module explaining *why* it isn't a knowledge
    writer — in prose that names "assertion" or "evidence" — isn't flagged for
    saying so.
    """
    forbidden = KNOWLEDGE_TABLES - allowed
    tree = ast.parse(source)
    prose = _docstrings(tree)
    referenced = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "schema"
    }
    if referenced & forbidden:
        return True
    strings = " ".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose
    )
    return any(re.search(rf"\b{table}\b", strings) for table in forbidden)


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
        # Method form on a table, and module paths the plain `sa.insert` check missed.
        "conn.execute(schema.entity.insert().values(name='x'))",
        "conn.execute(schema.edge.update().where(c))",
        "conn.execute(schema.assertion.delete())",
        "import sqlalchemy as sa\nsa.sql.insert(t)",
        # DML that is not at the very start of the string.
        "q = '-- note\\nINSERT INTO entity(name) VALUES (1)'",
        "q = 'BEGIN; INSERT INTO entity VALUES (1)'",
        "q = 'WITH x AS (SELECT 1) INSERT INTO entity SELECT * FROM x'",
        "q = 'INSERT OR REPLACE INTO entity VALUES (1)'",
        "q = 'INSERT OR IGNORE INTO edge VALUES (1)'",
        "q = 'UPDATE \"entity\" SET name = 1'",
        "q = 'UPDATE main.entity SET name = 1'",
        "q = 'UPDATE OR ROLLBACK entity SET name = 1'",
        # Driver-level escape hatches that skip the SQLAlchemy constructs entirely.
        "cursor.executemany(q, rows)",
        "conn.executescript(script)",
        "raw.exec_driver_sql(q)",
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
        # A read on the same chains the write checks look at.
        "conn.execute(schema.entity.select())",
        "sa.sql.select(t)",
        # Prose that mentions the words without being DML.
        "s = 'we insert into the plan and then update it'",
        "s = 'PRAGMA foreign_keys = ON'",
        "cursor.execute('PRAGMA foreign_keys=ON')",
    ],
)
def test_the_scanner_ignores_reads_and_unrelated_calls(snippet: str) -> None:
    assert writes_in(snippet) == []


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("import sqlite3", True),
        ("import sqlite3 as db", True),
        ("from sqlite3 import connect", True),
        ("import sqlalchemy", False),
        ("from cvforge.kb import sqlite3_helpers", False),
    ],
)
def test_the_sqlite3_scanner_sees_every_import_form(snippet: str, expected: bool) -> None:
    assert imports_sqlite3(snippet) is expected


@pytest.mark.parametrize(
    "path",
    [path for path in _all_non_exempt_modules() if path not in SQLITE3_MODULES],
    ids=lambda p: str(p.relative_to(SRC)),
)
def test_only_the_engine_and_the_export_use_the_sqlite3_driver(path: Path) -> None:
    """The driver can write without SQLAlchemy at all — registered writers are checked too."""
    assert not imports_sqlite3(path.read_text(encoding="utf-8")), (
        f"{path.relative_to(SRC)} imports sqlite3. Only kb/db.py (the connect-time "
        "pragma) and kb/export.py (the backup API) may."
    )


def test_the_writer_itself_is_scanned_positive() -> None:
    """If this fails, the scanner is broken, not the invariant."""
    assert writes_in(WRITER.read_text(encoding="utf-8"))


# --- ADR-0011: registered writers of non-knowledge state ---------------------


@pytest.mark.parametrize("rel", sorted(REGISTERED_WRITERS), ids=lambda rel: rel)
def test_a_registered_writer_never_touches_a_knowledge_table(rel: str) -> None:
    source = (SRC / rel).read_text(encoding="utf-8")
    assert not references_knowledge_table(source, REGISTERED_WRITERS[rel]), (
        f"{rel} is registered to write {sorted(REGISTERED_WRITERS[rel])}, but references a "
        "knowledge table. Route the knowledge write through kb/apply.py instead."
    )


def test_registering_a_writer_is_a_visible_change() -> None:
    """Edit this set deliberately, in review — it is exactly the point of the registry."""
    assert set(REGISTERED_WRITERS) == {"llm/settings_store.py"}


# A fixed reference set, independent of KNOWLEDGE_TABLES' own derivation from
# REGISTERED_WRITERS: this must never shrink just because a future entry widens
# its allowance. If a new entity kind is added, add its table here too.
CORE_KNOWLEDGE_TABLES = frozenset(
    {
        "entity",
        "edge",
        "assertion",
        "source",
        "evidence",
        "proposal",
        "operation",
        "commit_log",
        "skill",
        "project",
        "organization",
        "role",
        "education",
        "credential",
        "achievement",
        "responsibility",
    }
)


def test_no_registered_writer_is_ever_allowed_a_knowledge_table() -> None:
    """`KNOWLEDGE_TABLES` is derived FROM `REGISTERED_WRITERS`, so it can't catch this by itself:

    a value naming a core table would just shrink what counts as "knowledge"
    right along with it. This checks against a fixed set instead.
    """
    for rel, allowed in REGISTERED_WRITERS.items():
        overreach = allowed & CORE_KNOWLEDGE_TABLES
        assert not overreach, f"{rel} is registered to write {sorted(overreach)}, a knowledge table"


@pytest.mark.parametrize(
    ("source", "allowed", "expected"),
    [
        ("schema.app_setting.insert()", frozenset({"app_setting"}), False),
        ("schema.entity.insert()", frozenset({"app_setting"}), True),
        (
            "conn.execute(sa.text('INSERT INTO app_setting VALUES (1)'))",
            frozenset({"app_setting"}),
            False,
        ),
        (
            "conn.execute(sa.text('INSERT INTO entity VALUES (1)'))",
            frozenset({"app_setting"}),
            True,
        ),
    ],
    ids=["own-table-attr", "knowledge-table-attr", "own-table-string", "knowledge-table-string"],
)
def test_the_registered_writer_scanner_sees_a_reference_either_way(
    source: str, allowed: frozenset[str], expected: bool
) -> None:
    assert references_knowledge_table(source, allowed) is expected


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
