---
name: kb-schema
description: Change the knowledge-base schema (entities, edges, provenance, proposals) without breaking the invariants. Use when adding or altering an entity kind, a relationship type, a provenance table, or a migration, or when a write path needs to change.
---

# Changing the knowledge schema

This is the highest-risk area in the repository. The knowledge base is the source
of truth about a real career; a schema change that weakens an invariant silently
destroys the property that makes the whole system worth using.

Read `docs/architecture/knowledge-model.md` and ADR-0001 before touching anything.

## The invariants a change must preserve

1. **One write path.** `src/cvforge/kb/apply.py` is the only module that writes
   `entity`, `edge` or `assertion` rows. New mutation logic goes *there*, not
   wherever it is convenient. How `apply.py` talks to SQLite is a separate,
   still-open decision (issue #51) — nothing in this invariant depends on the
   answer, and this skill does not presume one.
2. **Every entity and edge has ≥1 assertion** bound to an `evidence` span in a
   `source`. A new entity kind needs no new provenance mechanism — it needs to use
   the existing one.
3. **Relationships live only in `edge`.** No entity table gets a foreign key to
   another entity. An education's institution, a role's employer and a credential's
   issuer are all `at_organization` edges.
4. **`rel` is a closed vocabulary**: `used_in`, `at_organization`, `produced`,
   `involved`, `demonstrates`, `taught_by`, `part_of`, `related_to`. Adding a value
   is a **design decision and needs an ADR** — it changes what the system can mean.
5. **Nothing writes without review.** A new fact source means a new `Proposal`
   origin and a new operation classification path, not a bypass.

## Procedure

1. **Search first.** `search_graph` for an existing model, column or helper that
   already covers it. Duplication is the primary failure mode here.
2. **Decide whether it is a decision.** New entity kind, new `rel` value, new
   provenance semantics, or a change to what "confirmed" means → write an ADR with
   the `adr` skill before the code.
3. **Write the migration.** Additive where possible. A destructive migration must
   be reversible or must export first — the user's knowledge base is irreplaceable
   and is not in version control.
4. **Update `apply.py` and its invariant tests together.** A new kind that
   `apply.py` cannot write is dead schema; a new kind `apply.py` writes without an
   assertion is a broken invariant.
5. **Update the diagram.** `docs/architecture/knowledge-model.md` depicts the
   model; a schema change that leaves it stale fails `doc-curator`.
6. **Re-run the invariant suite**, not just the new test:
   `uv run pytest tests/integration/test_invariants.py -v`

## Red flags

| You are about to… | Stop, because… |
|---|---|
| write to the database from anywhere outside `apply.py` | that is the one rule with three enforcement mechanisms; it will fail review |
| give an entity table an FK to another entity | relationships live in `edge`; two places to traverse means two places to forget |
| invent a `rel` value inline | the vocabulary is closed; widening it is an ADR |
| write an entity in a test without an assertion | the test will pass and the invariant test will fail — fix the helper, not the invariant |
| drop or rename a column in a migration | the user's real knowledge base is the only copy; export first |
