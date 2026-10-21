# 0029. Learning plans are advice; completing one only proposes a state change

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-33 drafts a learning plan for a `gap` requirement; FR-34 tracks progress and moves an entity
from `learning` toward `confirmed`. A skill becoming `confirmed` is knowledge about Álvaro, so it
must go through review (invariants 1, 2 and 4).

## Decision

**D-AV — a plan is advice, stored by a registered writer.** `learning_plan` (one per requirement,
linked to the posting, the `gap` requirement and, when one is recorded, the entity of that name) and
`learning_step` (title, kind `study|reading|exercise|project`, optional resource, `done_when`,
`completed_at`) are written by `learning/store.py` (ADR-0011). They carry no assertion. The plan
agent is tool-free, the requirement and the user's skill names fenced as data, and is told never to
invent resource titles or URLs. Only a stored `gap` verdict earns a plan (409 otherwise: an
`undocumented` requirement gets a discovery question instead).

**D-AW — tracking requires an entity already recorded as `learning`.** Completing a step against a
plan whose entity is missing or in any other state is refused (409) before anything is written; the
system never creates or relabels an entity to make tracking possible. Recording "I am learning X" is
an ordinary proposal (chat).

**D-AX — completion proposes, review decides.** When the last step is marked, `learning/progress`
records a manual source plus one evidence span ("all N steps were marked complete") and raises one
pending proposal with a single `set_state` (`learning` to `confirmed`) operation, remembered on the
plan so repeating a completion does not raise another. The entity changes only when the user accepts
and commits it. Steps are idempotent: re-completing keeps the first time.

## Consequences

- A completed plan is the user's own statement, not proof of skill; the evidence span says so. The
  review step is where Álvaro decides whether to believe it.
- Plans for requirements with no recorded entity can be drafted and read but not tracked until the
  skill is recorded as `learning`.
