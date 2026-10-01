# 0013. The similarity index is derived state, built lazily and rebuilt on a dimension change; the duplicate threshold is a tunable setting

Date: 2026-09-27
Status: proposed — in force from 2026-09-27 under Álvaro's `/goal` delegation ("take
the necessary decisions"); not yet reviewed by him. Confirm to mark it accepted.

> Part 1 covers D-D and D-G, decided for package B2 (embeddings and
> similarity search). Part 2 will add D-C, decided for package B3 (the
> `IngestAgent` and the chat endpoint), as an addendum to this same file
> when that package lands.

## Context

FR-05 asks for similarity search over entities so `kb.classify` can emit
`duplicate` for a differently-named but probably-the-same thing — until now,
only an injected test double could ever produce that verdict (`kb/classify.py`'s
own docstring said so). Two things needed a decision before `kb/embeddings.py`
could write real vectors and real distances:

1. **Where does the vector index live relative to the write path?** Embedding a
   name is a network call (to Ollama, by default). Invariant 2 already forces
   every knowledge write through `kb/apply.py`, and `apply._write_transaction`
   takes SQLite's write lock with `BEGIN IMMEDIATE` before it reads anything, so
   the transaction is held for the shortest possible time. A network call inside
   that lock would hold it for however long Ollama takes to respond — anywhere
   from milliseconds to a timeout — blocking every other reviewer/commit request
   against the same file for that whole span.
2. **What counts as "the same thing"?** Cosine similarity is a continuous score;
   `duplicate` is a binary verdict `kb.classify` has to store on the operation.
   The line has to sit somewhere, and it changes the failure mode on both sides:
   too low, and unrelated entities merge; too high, and obvious duplicates pile
   up as separate rows for a reviewer to notice by hand later.

## Decision

**D-D — the index is derived, disposable state, and no embedding call ever runs
inside a write transaction that holds the knowledge base's write lock.**

- `entity_vec`, a `sqlite-vec` `vec0` virtual table, is a registered writer
  (ADR-0011) of exactly one table — never a knowledge table, never referenced
  through `kb.schema` (indexing code reads entity names through `kb.queries`
  instead, the same read surface every other consumer uses).
- `ensure_index(engine, dimension)` creates it if missing or rebuilds it (drop,
  recreate) if the table's recorded dimension — read back from
  `sqlite_master.sql`, which preserves the `float[N]` declaration verbatim —
  differs from what's asked for. A dimension change is a settings change
  (`embedding_model` in `ProviderSettings`), not a code change (FR-40).
- `index_entities`/`reindex_missing` open their own connection to embed and
  read, and only take the write lock (via a local `BEGIN IMMEDIATE`
  transaction, mirroring `apply._write_transaction`'s rationale) for the
  INSERT itself — never around the `provider.embed(...)` call.
- **Indexing happens after `commit_proposal` returns, never inside it.**
  `api/proposals.py`'s commit route calls `index_entities` on the newly
  created entity ids once the commit transaction has already closed. A failed
  embedding call never fails the commit or loses data: `index_entities` never
  raises `EmbeddingError`, only reports the ids it couldn't embed, and the
  commit response carries them as `index_pending` — the commit stands, and
  `reindex_missing` (run once at real app startup, and available to run again)
  catches them up later.
- `reindex_missing` checks whether there is anything to index *before* it
  reads the embedder's `dimension` at all. This is not an optimization; it's
  what makes "no embedder configured" (`app.state.embedder is None`, or an app
  built for tests against an empty database) genuinely free of embedding
  calls, rather than merely usually fast.

**D-G — the default duplicate threshold is 0.85 cosine similarity, stored in
`ProviderSettings.similarity_threshold` so it is tunable without a code
change.** Conservative on purpose: a false `duplicate` silently links two
different things and the merge has to be noticed and undone later; a missed
`duplicate` just creates an extra row a reviewer catches at review time, which
is the review pipeline's whole job (ADR-0009). 0.85 is a starting point to
tune against real use, not a value derived from a benchmark — there is no
labelled dataset of "same skill, different name" pairs to tune it against yet.

## Alternatives considered

- **Embed inside `apply.commit_proposal`'s write transaction, so the index is
  never stale.** Rejected. This is exactly the failure mode invariant 2's own
  `_write_transaction` docstring warns about for a different reason (holding
  the lock on a check-then-act race) — here it would hold the lock for the
  duration of a real network call, serializing every commit behind however
  long Ollama takes to respond. A stale index that catches up moments later
  costs far less than every other request queuing behind one slow embed.
- **A fixed embedding dimension, hardcoded once.** Rejected — FR-40 explicitly
  asks for a pluggable provider, and different embedding models emit different
  dimensions (`nomic-embed-text` is 768; not every model is). Reading the
  dimension back from `sqlite_master.sql` avoids a second metadata table just
  to track a number SQLite already remembers for the virtual table's own
  column declaration.
- **A second `entity_vec_meta` table recording the current dimension.**
  Rejected for now (ADR-0011's own note left this open). `sqlite_master.sql`
  already carries `float[N]` verbatim once the table exists, so a dedicated
  metadata table would duplicate a fact SQLite already stores, for no benefit
  over a two-line regex. Revisit if a future need (recording *when* the index
  was last rebuilt, say) needs a row and not just the current dimension.
- **A single hardcoded threshold with no settings field.** Rejected. FR-38/
  FR-39's whole point is that provider behavior is runtime-tunable without a
  redeploy; a threshold that turns out too aggressive or too conservative in
  practice should be a settings change Álvaro can make from the UI (C1.6),
  not a PR.
- **Fail the commit when an entity can't be embedded.** Rejected. Indexing is
  a search-quality concern, not a provenance one — invariants 2 and 3 are
  about what gets written and why, and a missing search-index row violates
  neither. Failing the commit over it would make the review pipeline's
  correctness depend on an unrelated network service being up.

## Consequences

- A commit is never slower because of the embedding endpoint: worst case, it
  reports `index_pending` and the search index catches up later.
- `find_similar`'s own contract (raises `EmbeddingError`, callers decide) and
  `make_similar_finder`'s contract (degrades to `None`, never raises) are
  deliberately different: `kb.classify`'s `similar` argument must never turn
  a down embedder into a classification failure, while a direct caller of
  `find_similar` (a future UI search box, say) may reasonably want to show an
  error instead of silently returning nothing.
- Changing `embedding_model` (hence the dimension) rebuilds `entity_vec` from
  scratch on the next `ensure_index` call and re-embeds every entity through
  `reindex_missing` — acceptable for a personal knowledge base's scale (low
  hundreds to low thousands of entities), revisit if that stops being true.
- `similarity_threshold` has no enforcement beyond Pydantic's `ge=0, le=1` on
  `ProviderSettings` (already covered by B1.3's own tests) — this ADR does not
  add a new constraint, only a rationale for the shipped default.
