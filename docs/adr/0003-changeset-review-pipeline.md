# 0003. Agents propose changesets; they never write to the knowledge base

Date: 2026-09-12
Status: accepted

## Context

The knowledge base is meant to be the source of truth about a real career. The
failure mode that would destroy its value is an LLM gradually inventing or
quietly altering facts — a team of five becoming a team of fifteen, a course
becoming a certification, a skill appearing because it fitted a job posting. Any
design that relies on prompt wording to prevent this will eventually fail.

## Decision

We will give agents **no write capability at all**. An agent's only output is a
`Proposal`: an ordered list of typed operations (`create_entity`, `update_field`,
`add_edge`, `attach_evidence`, `merge_duplicate`, `set_state`), each carrying the
evidence span it came from and a classification (`new`, `known`, `duplicate`,
`conflict`). Álvaro accepts, edits or rejects **each operation individually**.
Committing applies the survivors in one transaction through `kb/apply.py`, the
only module in the codebase that writes entity, edge or assertion rows, and
records the commit.

## Alternatives considered

- **Direct agent writes with a journal and undo.** Far less machinery and a
  snappier feel. Rejected: review becomes after-the-fact, duplicate and conflict
  detection lose their natural home, and the system would no longer do the thing
  that was asked for — show what it understood *before* storing anything.
- **A staging schema promoted on accept.** Conceptually tidy, but every read path
  then has to know which store it is reading, and cross-store duplicate detection
  pushes the complexity into the read path, where it is worst.

## Consequences

- One review surface serves conversational ingest, document ingest and interview
  mode: three features, one UI, one audit trail.
- A proposal is plain data, so the entire pipeline is testable with no model
  involved — which is what makes the 90% coverage floor and the golden suite
  achievable.
- Every write costs a round trip through review. For bulk document import that is
  friction by design.
- The rule is only as strong as its enforcement, so it is enforced three ways: an
  invariant test, the `provenance-auditor` agent, and the `kb-write-path` hook.
