# 0010. M1a storage and gate policies: rollback journal, and migrations outside the write scan and the coverage floor

Date: 2026-09-26
Status: proposed — in force from 2026-09-26 under Álvaro's `/goal` delegation ("take the necessary decisions"); not yet reviewed by him. Confirm to mark it accepted.

## Context

PR #68 (M1a, the knowledge store) settled three policies without recording them.
The `doc-curator` audit of that PR found each one and noted that no ADR covers it:

1. Which SQLite journal mode the knowledge base runs in.
2. Whether Alembic revisions count towards the 90% coverage floor.
3. Whether Alembic revisions are subject to the "no write outside `kb/apply.py`"
   scan (invariant 2).

The second and third quietly narrow two project rules, so they need a visible
record. A decision without an ADR does not exist.

## Decision

1. **The database keeps SQLite's default rollback journal, not WAL.** WAL adds
   `-wal` and `-shm` files next to `cvforge.db`, and NFR-09 requires the knowledge
   base to be one file that can be copied and inspected. `kb/db.py` documents this
   on `make_engine`, and `tests/integration/test_db_export.py` asserts the data
   directory holds `cvforge.db` and nothing else. A consistent copy of a running
   database comes from the export command, which uses the SQLite backup API.
2. **Alembic revisions are omitted from the coverage measurement**
   (`omit = ["src/cvforge/kb/migrations/*"]`). They are generated DDL run by
   Alembic. The gate on them is `tests/integration/test_migrations.py`, which
   fails when `schema.py` and the migrated head disagree, and which upgrades a
   populated database without losing rows.
3. **`kb/migrations/` is exempt from the invariant-2 write scan.** A revision is a
   schema change, not a knowledge write. A revision that needs to move data (a
   backfill for a new NOT NULL column, say) is legitimate there and only there,
   and is a design decision reviewed in its own PR.

The literal wording "every insert, update and delete in `src/` lives in
`kb/apply.py`" (ADR-0006, the `apply.py` module docstring, the `kb-schema` skill)
therefore reads, from now on, "…except Alembic revisions".

## Alternatives considered

- **WAL mode.** Rejected. It is faster under concurrent readers and writers, which
  a single-user local tool does not have, and it costs the one-file property that
  NFR-09 states as a requirement.
- **WAL with a checkpoint on shutdown.** Rejected. The side files exist for as
  long as the app runs, which is exactly when someone is most likely to copy
  `data/` by hand, and the result of copying only `cvforge.db` would be a
  database missing recent writes.
- **Count migrations in coverage.** Rejected. Unit runs never execute them, so the
  floor would fail, and the only way to raise it is a test that executes generated
  DDL to execute generated DDL, which proves nothing the drift test does not.
- **Per-line `# pragma: no cover` in each revision.** Rejected. It repeats the
  same exemption in every future file and hides that it is a policy.
- **Scan migrations for writes too.** Rejected. It would force a per-revision
  exemption for every legitimate data migration, and an exemption granted line by
  line is easier to grant carelessly than a directory-level rule that names itself
  in one test.

## Consequences

- The knowledge base stays one file, and `make run` leaves only `cvforge.db` and,
  after a migration, `backups/`.
- The coverage number describes the code Álvaro maintains by hand. A new revision
  cannot raise or lower it, and cannot be checked by it either, so the drift test
  is the only protection and must stay in the required CI set.
- The `provenance-auditor` must treat a revision containing DML as a review item,
  not a pass.
- ADR-0011 (registered writers for non-knowledge state, in the M1b plan) builds on
  the same idea: exemptions are named, in one place, in a test.
