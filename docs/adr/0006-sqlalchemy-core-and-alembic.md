# 0006. SQLAlchemy Core plus Alembic for the knowledge layer

Date: 2026-09-20
Status: accepted

## Context

ADR-0001 fixed the store: SQLite, joined-table inheritance for entity kinds, a
generic `edge` table, `sqlite-vec` for embeddings. It deliberately did **not**
say how Python talks to that database, and the question was tracked as issue
\#51. Until now nothing has been built on top of it, so the cost of deciding
late was zero and the cost of deciding wrong was high.

Three things constrain the answer.

**The schema will change repeatedly, and that is expected, not a risk.** This is
a system that learns what one person knows; the entity kinds, the relationship
vocabulary and the provenance tables will be reshaped as it is actually used
against a real career. Any approach that makes the second or third reshape
painful is disqualified, however well it handles the first.

**Invariant 2 has to be enforceable by inspection, not by discipline.**
`src/cvforge/kb/apply.py` is the only module that may write `entity`, `edge` or
`assertion` rows. That invariant is checked three ways — a test, the
`provenance-auditor` agent, and the `kb-write-path` hook — and all three work by
recognising a write when they see one. An access layer whose writes are implicit
is an access layer where those checks are guesses.

**`mypy --strict` passes over `src`, and coverage has a 90% floor.** Whatever is
chosen has to be typed well enough to survive strict mode without a wall of
`type: ignore`, and simple enough that its error paths are reachable in tests.

## Decision

**SQLAlchemy Core for queries and writes, Alembic for migrations. No ORM
session, no declarative models, no identity map.**

- Tables are declared as `sqlalchemy.Table` objects in one schema module.
- Reads live in `kb/queries.py` and return plain dataclasses or `TypedDict`s,
  never live database-bound objects.
- Every `insert()`, `update()` and `delete()` construct in `src/cvforge/` lives
  in `kb/apply.py`. Nothing else constructs one.
- Schema changes go through `alembic revision`, are reviewed as ordinary code,
  and are applied on startup after a backup of the database file.
- `sqlite-vec` is loaded through an engine-level connect listener, so the
  extension is available to Core statements without a second connection path.

## Alternatives considered

**SQLAlchemy ORM plus Alembic.** Rejected, and it is the close call. The ORM
would give joined-table inheritance for free, which ADR-0001's entity model
genuinely wants, and SQLAlchemy 2.0's `Mapped[]` annotations type well. It was
rejected because of the unit of work: with a `Session`, a write happens when an
attribute is assigned on a loaded object and a flush occurs later, somewhere
else. That is precisely the shape invariant 2 forbids, and it is invisible to a
grep, to the hook and to the auditor agent. Choosing the ORM would mean
enforcing the project's central invariant by convention, in the one module where
convention is least trustworthy. The joined-table inheritance is then written by
hand as explicit joins in `queries.py` — more code, but code that says what it
does.

**Stdlib `sqlite3` with hand-rolled migrations.** Rejected on the first
constraint. It is the lightest thing that works for version 1 of a schema and
the heaviest thing that works for version 4: every migration becomes a
bespoke script, ordering and idempotence are re-solved each time, and there is
no `alembic autogenerate` diff to review. Given that repeated reshaping is
expected, this concentrates effort exactly where it will be spent most often.
Alembic is the reason to accept the SQLAlchemy dependency at all.

**Deferring the decision further.** Rejected because M1 builds the knowledge
layer, so the first line of `apply.py` decides this whether or not an ADR says
so — and then it is decided by accident, in a file, with no record.

## Consequences

- The dependency set gains `sqlalchemy` and `alembic`. Both are pinned by the
  lock file and covered by the `pip-audit` context.
- Writes become greppable. `kb-write-path.sh` and the `provenance-auditor` agent
  can look for `insert(`, `update(`, `delete(` and raw DML and be confident that
  what they do not see does not exist. Their patterns stay deliberately broad —
  they also match stdlib `sqlite3` idioms — because a module that reaches for a
  raw cursor is exactly the case worth catching.
- Joined-table inheritance costs explicit joins in `queries.py`. If that becomes
  the dominant source of complexity, the answer is a new ADR superseding this
  one, not a quiet reintroduction of the ORM.
- Every schema reshape produces a reviewable migration file. Applying one
  without a backup of the database file is a bug: the real knowledge base is the
  only copy.
- Issue \#51 closes with this ADR.
