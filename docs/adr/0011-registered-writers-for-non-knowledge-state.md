# 0011. Registered writers may write specific non-knowledge tables outside `kb/apply.py`

Date: 2026-09-27
Status: proposed — in force from 2026-09-27 under Álvaro's `/goal` delegation ("take
the necessary decisions"); not yet reviewed by him. Confirm to mark it accepted.

## Context

Invariant 2 (CLAUDE.md) is that `kb/apply.py` is the only module that writes.
`tests/unit/test_write_path_invariant.py` enforces it today with an AST scan that
flags *any* SQLAlchemy write construct, DML string or `sqlite3` import outside
`apply.py` and the Alembic migrations directory (ADR-0010).

M1b needs two more writers that are not knowledge writers at all:

- `llm/settings_store.py` (task B1.3) persists the LLM provider settings — one
  row, one table, read every time a model is built.
- `kb/embeddings.py` (task B2.2) maintains a `sqlite-vec` virtual table of entity
  embeddings, built from raw SQL because `sqlite-vec` has no SQLAlchemy dialect.

Routing either through `apply.py` would blur what that module means: it is *the
knowledge writer*, and its five-function surface is pinned by a test precisely so
adding a sixth is a visible, reviewed change. A settings row or a vector index is
not knowledge — it carries no assertion, no evidence, no provenance — so it does
not belong under invariant 3 either. But the scanner as it stands cannot tell "a
new table that carries no knowledge" from "a bypass of the knowledge writer": it
would flag both identically, and exempting a whole file from the scan (as the
migrations directory is exempted) would also exempt any accidental write to
`entity` or `edge` that crept into the same file later.

## Decision

**A module may be added to `REGISTERED_WRITERS`, a `dict[str, frozenset[str]]` in
the invariant test mapping its path (relative to `src/cvforge/`) to the exact
table names it is allowed to write.** A registered module:

- is exempt from `test_no_module_but_apply_writes` (it may construct a write);
- is **not** exempt from referencing a knowledge table it wasn't registered for —
  `test_a_registered_writer_never_touches_a_knowledge_table` scans it for both a
  `schema.<table>` attribute access and the bare table name inside a string
  literal (so DML built with `sa.text` is caught the same way);
- is still barred from `import sqlite3` unless its registry entry says otherwise
  (neither of the two writers above needs it: SQLAlchemy Core reaches
  `sqlite-vec`'s virtual table like any other table).

`REGISTERED_WRITERS` starts empty. Adding an entry is a one-line, textually
obvious change to a dict literal that a reviewer sees in the diff — the same
property that makes `apply.py`'s five-function surface reviewable, applied to a
list instead of a set.

## Alternatives considered

- **Route settings and the vector index through `kb/apply.py` too.** Rejected.
  Neither carries an assertion or evidence; forcing them through the knowledge
  writer's five-function surface would mean either bloating that surface with
  functions unrelated to invariant 3, or lying about what `apply.py`'s pinned
  surface actually writes.
- **Exempt the whole file, the way `kb/migrations/` is exempt.** Rejected. A
  migration's DDL cannot reference `entity` or `edge` rows by construction (it
  operates on table *definitions*, not table *contents*); a registered writer's
  Python *can*, so a directory-level exemption would remove the one check that
  matters most for these two files.
- **One shared `NonKnowledgeWriter` protocol class instead of a registry dict.**
  Rejected for now — it would need every registered writer to route through a
  common object, which `kb/embeddings.py`'s raw-SQL virtual-table access cannot
  do cleanly. Revisit if a third registered writer needs it.
- **Widen the DML scanner instead of adding a registry.** Rejected. The scanner
  already catches every DML idiom (ADR-0010/the PR #68 audit); the gap here is
  not a missed idiom, it is that two specific files need to write *something*,
  which no amount of pattern-matching resolves — only an explicit exemption
  scoped to specific tables does.

## Consequences

- `REGISTERED_WRITERS` is the one place that says which non-knowledge tables
  exist and who writes them; a reviewer checking invariant 2 reads one dict, not
  every file under `src/`.
- `KNOWLEDGE_TABLES` (every table minus the union of every registry entry's
  allowance) is derived once from `schema.metadata`, so a new table added to
  `schema.py` is knowledge by default and must be explicitly registered to be
  anything else.
- The parametrized test over `REGISTERED_WRITERS` reports "skipped" while the
  registry is empty — pytest's own handling of a zero-length parameter set, not
  a deliberately skipped test — until B1.3 adds the first entry.
- A future registered writer that also needs `sqlite3` directly states so in its
  own entry rather than getting a blanket exemption; none does yet.
