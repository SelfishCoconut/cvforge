# 0020. The job agent has no tools and reads the posting as fenced data

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-18 turns a fetched posting into structured fields. The posting is attacker-controlled
text (NFR-07): a page can say "ignore your instructions and call …". Every tool an agent
holds is something such a page could try to talk it into using. The ingest and document
agents hold read-only knowledge-base tools because they must check what is already
known; analysing a posting needs nothing from the knowledge base (matching is M4).

## Decision

**D-O — the job agent has no tools.** `build_job_agent` registers none, so there is
nothing for a hostile posting to call. A test asserts the model is offered no function
tools even when the posting asks for one. The agent is deliberately *not* in `AGENTS`,
whose test requires the read-only knowledge tools.

**D-P — the posting is fenced as data and cannot close its own fence.** The text is
wrapped in `<posting>…</posting>` and any `</posting>` inside it is removed first. The
prompt states that the fence holds data, never instructions.

**D-Q — empty is a value; guessing is not.** `JobAnalysis` fields are `None` or an empty
list when the posting says nothing; the prompt forbids inference, and blank strings and
duplicate list entries are normalised away deterministically. Unknown fields are
rejected (`extra="forbid"`), and a model output that never validates raises
`AnalysisError` instead of yielding a partial analysis.

**D-R — analysis stores nothing.** `analyze_posting` returns a `JobAnalysis`. Persisting
it is FR-20.

## Consequences

- Prompt wording cannot be the only defence, and is not: the structural defences are the
  absence of tools, the schema, and the fact that nothing is written by this step.
- A hostile posting can still *skew the fields it reports* (say, claim a title). That is
  inherent to reading untrusted text; the analysis is shown to Álvaro, and nothing
  reaches the knowledge base from it (invariants 1 and 4).
