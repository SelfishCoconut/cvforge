# Architecture Decision Records

Decisions are recorded in [MADR](https://adr.github.io/madr/) format, one file
per decision. A decision without an ADR does not exist — these are the durable
record of *why*, and the context that survives a cleared conversation.

Supersede, never rewrite: a changed decision gets a new ADR linking back.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-sqlite-knowledge-store.md) | SQLite knowledge store with a generic edge table | accepted | 2026-09-12 |
| [0002](0002-single-process-api-and-spa.md) | One uvicorn process serves the API and the SPA | accepted | 2026-09-12 |
| [0003](0003-changeset-review-pipeline.md) | Agents propose changesets; they never write | accepted | 2026-09-12 |
| [0004](0004-srs-is-the-source-of-requirement-text.md) | The SRS is the source of requirement text | accepted | 2026-09-19 |
| [0005](0005-action-pinning-policy.md) | Third-party Actions that receive a token are pinned by digest | accepted | 2026-09-19 |
