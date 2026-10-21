# 0018. An edge between entities that resolve to stored ones is classified against the stored edge

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted. Amends ADR-0009 (classification).

## Context

ADR-0009 classifies an `add_edge` by looking up the stored edge between its endpoints.
Endpoints created in the same proposal are references (`OpRef`) to earlier operations, and
the classifier answered `new` for any `OpRef`. That is right when the entity is new, and
wrong when the entity classified `known` or `duplicate`: restating a fact together with
the edge that joins it to another gave `known, known, new`. Committing it then violated the
edge's unique key `(src_id, rel, dst_id)`, and because a commit is atomic the whole
proposal was refused. FR-16 (ingesting the same document twice must not duplicate anything)
found it; chat intake had the same latent fault.

## Decision

**D-P — `classify` takes the entities that earlier operations resolved to.**
`record_proposal` classifies operations in `seq` order and passes `classify` a map from the
`seq` of each earlier `create_entity` that classified `known` or `duplicate` to the stored
entity id. `_edge` resolves an `OpRef` end through that map; an end that is not in it is
still a new entity, so the edge is still `new`. A resolved edge then classifies exactly as
an edge between stored entities always did: `known`, or `conflict` when its dates differ.

**D-Q — the commit-time staleness check resolves the same way.** `_Committer._edge_matches`
resolves an `OpRef` end through the entity ids the committer has already applied, so a
`known` edge is not reported stale merely because its endpoints were references.

No write path changes: `kb/apply.py` still writes only what an accepted operation says,
and a `known` or `conflict` edge adds an assertion to the stored edge instead of inserting
one.

## Consequences

- Re-ingesting a document, or restating a message, commits cleanly and adds evidence only.
- A reviewer who rejects the `known` create but accepts its edge still gets the existing
  error that an unapplied operation cannot be referred to; this ADR does not change it.
- The map lives only inside one `record_proposal` call; nothing is persisted for it.
