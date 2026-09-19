# 0001. SQLite holds the knowledge base, with entity inheritance and a generic edge table

Date: 2026-09-12
Status: accepted

## Context

CVForge stores eight kinds of professional knowledge entity and arbitrary typed
relationships between them ("Python used in project X", "project X for company
Y", "project X produced achievement Z"), plus provenance for every fact. It is a
single-user, local-first tool whose whole premise is that private data stays on
one machine. The store has to support multi-hop traversal, duplicate detection by
meaning rather than string equality, and a backup story simple enough to actually
be used.

## Decision

We will use one SQLite file (`cvforge.db`) with:

- **Joined-table inheritance**: a base `entity` table holding the common columns
  and the `kind` discriminator, and one child table per kind. All entities share a
  single id space.
- **A generic `edge` table** (`src_id`, `rel`, `dst_id`, `confidence`, validity
  dates) with a closed `rel` vocabulary. No entity table holds a foreign key to
  another entity.
- **Provenance in three tables** — `source`, `evidence`, `assertion` — with every
  entity and edge requiring at least one assertion.
- **`sqlite-vec`** for embedding similarity, used for duplicate candidates and
  requirement matching.

## Alternatives considered

- **An embedded property graph (Kùzu) alongside SQLite.** Cypher traversals are
  more pleasant than recursive CTEs, but it means two stores to keep consistent,
  a less settled migration story, and documents/CV versions still needing SQLite.
  The traversals we actually need are two or three hops deep.
- **PostgreSQL with pgvector.** Mature migrations, relational and vector in one
  engine. Rejected because it requires a running service for a single-user local
  tool, and backup stops being "copy one file".
- **A single entity table with a JSON attribute blob.** Cheaper schema evolution,
  but it gives up column constraints and type checking on the data that matters
  most, and the set of entity kinds is known and stable.

## Consequences

- Backup, sync and reset are file operations. There is no service to run.
- Relationship queries are recursive CTEs. Anything deeper than a few hops will
  need a materialized closure table — acceptable, and not needed yet.
- Adding an entity kind means a migration adding a child table, which is a
  deliberate speed bump on a decision that deserves one.
- `sqlite-vec` is a compiled extension; loading it is a startup concern and must
  degrade to exact-match dedup when unavailable.
