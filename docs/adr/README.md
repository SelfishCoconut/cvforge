# Architecture Decision Records

Decisions are recorded in [MADR](https://adr.github.io/madr/) format, one file
per decision. A decision without an ADR does not exist — these are the durable
record of *why*, and the context that survives a cleared conversation.

Supersede, never rewrite: a changed decision gets a new ADR linking back.
Never edit an accepted ADR's decision after the fact — the record of what
was decided, and when, is the whole point.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-sqlite-knowledge-store.md) | SQLite knowledge store with a generic edge table | accepted | 2026-09-12 |
| [0002](0002-single-process-api-and-spa.md) | One uvicorn process serves the API and the SPA | accepted | 2026-09-12 |
| [0003](0003-changeset-review-pipeline.md) | Agents propose changesets; they never write | accepted | 2026-09-12 |
| [0004](0004-srs-is-the-source-of-requirement-text.md) | The SRS is the source of requirement text | accepted | 2026-09-19 |
| [0005](0005-action-pinning-policy.md) | Third-party Actions that receive a token are pinned by digest | accepted | 2026-09-19 |
| [0006](0006-sqlalchemy-core-and-alembic.md) | SQLAlchemy Core plus Alembic for the knowledge layer | accepted | 2026-09-20 |
| [0007](0007-material-native-mermaid.md) | Mermaid renders through Material's native support | accepted | 2026-09-20 |
| [0008](0008-close-m0-on-evidence-not-issues.md) | M0 closes on evidenced requirements; unevidenced NFRs move to M1 | accepted | 2026-09-21 |
| [0009](0009-review-pipeline-semantics.md) | Review-pipeline semantics: what is written when; the four classifications | accepted | 2026-09-21 |
