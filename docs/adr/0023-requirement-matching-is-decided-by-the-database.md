# 0023. Requirement matching is decided by the database; the model only judges adjacency

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-21 assigns each job requirement one of `satisfied | evidenced | undocumented | gap`
(spec §4.6). These verdicts decide what a CV may claim (invariant 5): `satisfied` and
`evidenced` may back a claim, `undocumented` and `gap` never may. A model that picks the
verdict directly could talk itself, or be talked by a posting, into a claim the knowledge
base does not support (invariant 1).

## Decision

**D-AA — verdicts come from rules over the database** (`match/verdicts.py`):
- `satisfied`: a confirmed entity, of any kind, with the requirement's normalised name and
  at least one `used_in` / `demonstrates` edge (every edge has an assertion, invariant 3).
- A recorded entity in state `gap` or `learning` is a `gap`; a confirmed one with no
  recorded use is `undocumented`; archived entities are ignored.
- `evidenced`: no entity of that name, but a confirmed, used entity whose embedding is at
  or above the similarity setting (default 0.85) of the requirement, or one a judge
  names (D-AB).
- `undocumented`: similar to the profile at or above a 0.6 floor but nothing states it.
- `gap`: nothing close, or similarity was unavailable (and the rationale says so).

**D-AB — an optional judge infers adjacency, and code validates it.** For requirements in
the band between the floor and the threshold, a tool-free model (`llm/agents/adjacency.py`,
the requirement fenced as data) is shown only the confirmed, used candidates the engine
found and may pick among them ("a framework implies its language"). Its answer is used only
if every id is one it was offered, at least one is chosen and the rationale is not blank;
otherwise the requirement stays `undocumented`. The model can lift a verdict only to
`evidenced`, never to `satisfied`, and never to an entity it was not offered.

**D-AC — matches are stored, per requirement, by a registered writer.** `match` holds the
verdict, score and rationale; `match_support` the backing entity ids (empty for
`undocumented` and `gap`). This departs from the spec's single `entity_id` column because a
verdict can rest on several entities. `match/store.py` is registered (ADR-0011) for those
two tables; a new run replaces a posting's matches in one transaction. Matches are derived
state and carry no assertion.

## Consequences

- Matching is only as good as the names in the knowledge base; "PostgreSQL" does not
  match a recorded "Postgres" unless similarity (or the judge) bridges them.
- Matches go stale when the knowledge changes; running the match again refreshes them.
- With no embedder configured only exact names can be `satisfied`; everything else is
  `gap`. That errs toward never over-claiming.
- Reads resolve a verdict's support at request time (`match/evidence.py`): each cited
  entity comes with the spans stating it and its recorded uses, an entity archived since
  the match is flagged (`archived`), and one that no longer exists is dropped rather than
  cited. The gap report (`undocumented` + `gap`) is read from the stored matches, in
  requirement order, so it is identical until the match is run again.
