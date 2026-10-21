# 0021. Job postings are a registered writer, keyed by normalised URL

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-20 persists a fetched, analysed posting as a `job_posting` row plus one `requirement`
row per item. A posting is information *about a job*, not knowledge about Álvaro: it
carries no assertion and no evidence. Invariant 2 reserves `kb/apply.py` for entity,
edge and assertion rows.

## Decision

**D-S — `jobs/store.py` is a registered writer** (ADR-0011) of `job_posting` and
`requirement` only. The write-path test registers it; it may not reference a knowledge
table. Its raw page stays traceable: each persist records a `web` source through
`kb.apply.record_source` and `job_posting.source_id` points at it.

**D-T — one posting per normalised URL.** The key lower-cases scheme and host, drops a
default port and the fragment, and keeps path and query (boards identify postings by
them). Persisting a stored URL updates the row in place: it keeps its id, takes the new
analysis, raw text, `fetched_at` and source, and its requirements are replaced by the
new set, in one transaction. Each fetch still adds a `source` row, so history is kept
there.

**D-U — decomposition is fixed.** Required skills, stated experience and other
requirements become `required`; preferred skills `preferred`; responsibilities
`responsibility`. A text repeated within a kind is stored once. The kind set is closed by
a CHECK constraint.

**D-V — `organization_id` and `normalized_skill_id` stay empty.** They link to knowledge
entities and are filled by matching (M4), never by a fetch, so a posting cannot create
or alter an entity.

## Consequences

- Re-fetching a posting changes requirement ids. Anything that later points at a
  requirement (M4 matches) must be recomputed on a re-fetch, which is the intent: the
  posting changed.
- Two URLs for one posting (tracking parameters) are two postings. Resolving that is a
  later, visible decision, not a silent merge.
