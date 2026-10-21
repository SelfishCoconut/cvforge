# 0022. Job intake is one request; company research is returned, not persisted

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

M3 delivers "URL → fetch → structured posting". FR-17 (fetch), FR-18 (analysis), FR-19
(research) and FR-20 (persistence) are separate units; something has to run them in
order, and tests must be able to replace the two that touch the outside world.

## Decision

**D-W — `POST /api/jobs {url}` runs fetch → analyse → (research) → persist as one
request.** It answers 201 for a new posting and 200 when the URL was already stored (the
row is updated, ADR-0021). `GET /api/jobs` and `GET /api/jobs/{id}` read postings back.
A fetch refusal or failure is 422 and a model that returns no valid analysis is 502;
neither stores anything.

**D-X — the fetcher and the search provider hang off `app.state`** (`job_fetcher`,
`search_provider`), as `model_factory` does. The default fetcher is static-first with the
Playwright fallback; the default search provider is `None`, so research is off until
Álvaro opts in. Tests and demos replace both, so nothing reaches the network.

**D-Y — research is returned in the response of the call that ran it and is not
persisted.** `job_posting` has no column for it, results are untrusted web text, and it is
cheap to redo. Persisting it, if wanted, is a schema decision for later.

**D-Z — NFR-07 for postings is pinned by a golden test.** `tests/golden/` replays a
benign and a hostile posting through the real HTTP layer and snapshots the stored result
and the tools the model was offered (none).

## Consequences

- Taking in a posting blocks for a fetch and a model call; the UI must show progress.
- A posting is analysed by whatever model is configured. A weak model produces a poor
  analysis, not an unsafe one: nothing it says reaches the knowledge base.
