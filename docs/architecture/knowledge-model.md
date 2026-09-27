# Knowledge model

The tables are declared in `src/cvforge/kb/schema.py` (SQLAlchemy Core, ADR-0006)
and created by the Alembic revisions in `src/cvforge/kb/migrations/versions/`.
Ids are integers, and all entity kinds share one id space.

```mermaid
erDiagram
  ENTITY ||--o| KIND_TABLE : "joined-table child (one per kind)"
  ENTITY ||--o{ EDGE : "src"
  ENTITY ||--o{ EDGE : "dst"
  SOURCE ||--o{ EVIDENCE : contains
  EVIDENCE ||--o{ ASSERTION : supports
  ASSERTION }o--|| ENTITY : "targets (target_kind=entity)"
  ASSERTION }o--|| EDGE : "targets (target_kind=edge)"
  SOURCE ||--o{ PROPOSAL : "derived from"
  PROPOSAL ||--o{ OPERATION : contains
  PROPOSAL ||--o{ COMMIT_LOG : "committed as"

  ENTITY { int id string kind string name string normalized_name string summary string state }
  KIND_TABLE { int id "skill, project, organization, role, education, credential, achievement, responsibility" }
  EDGE { int id int src_id string rel int dst_id float confidence date started_at date ended_at }
  SOURCE { int id string kind string label string uri string content_hash }
  EVIDENCE { int id int source_id string locator string excerpt }
  ASSERTION { int id string target_kind int target_id string field json value_json int evidence_id }
  PROPOSAL { int id string origin int source_id string status string summary }
  OPERATION { int id int seq string op_type json payload_json string classification string target_kind int target_id string status json edited_payload_json }
  COMMIT_LOG { int id int proposal_id json operation_ids_json }
```

Three references cannot carry a foreign key, so each is checked another way:

- `assertion.target_id` is polymorphic (an entity or an edge). `queries.orphans()`
  and `tests/integration/test_invariants.py` check it.
- `operation.target_kind` / `operation.target_id` name an entity or an edge in the
  same polymorphic way. `OperationDraft` checks the pair's shape (both set or
  neither, matching the classification), and `commit_proposal` raises
  `NotFoundError` if the named target is missing when it applies the operation.
- `operation.payload_json` carries an `evidence_id` inside JSON. `record_proposal`
  checks that the cited evidence exists before any operation is stored.
- `commit_log.operation_ids_json` is a JSON list of the operation ids applied. It
  is written by `commit_proposal` in the same transaction as the operations it
  lists.

Every other reference is a real foreign key, enforced on every connection
(`PRAGMA foreign_keys = ON`), and every closed vocabulary is also a CHECK
constraint.

## Entity kinds

`skill` · `project` · `organization` · `role` · `education` · `credential` ·
`achievement` · `responsibility`. A *technology* is a `skill` with a category; a
*certification* and a *course* are both `credential` with different
`credential_type` values.

## Relationship vocabulary (closed — never invent a value)

`used_in` · `at_organization` · `produced` · `involved` · `demonstrates` ·
`taught_by` · `part_of` · `related_to`

No entity table carries a foreign key to another entity. An education's
institution, a role's employer and a credential's issuer are all
`at_organization` edges, so relationships live in exactly one place and are
evidenced the same way.

## Knowledge state vs match verdict

`entity.state` is `confirmed | learning | gap | archived`. "Something I have but
have not recorded" is deliberately **not** a state — it is a *match verdict*
(`undocumented`), because by definition such a thing is not in the database. The
four verdicts are `satisfied`, `evidenced`, `undocumented` and `gap`;
`undocumented` and `gap` may never produce a CV claim.

## The write path

```mermaid
flowchart LR
  A[Álvaro speaks / uploads / pastes a URL] --> B[Agent]
  B -->|reads only| KB[(cvforge.db)]
  B --> P[Proposal: typed operations<br/>each classified and evidenced]
  A -->|intake: record_source, record_evidence| W[kb/apply.py]
  P -->|record_proposal: proposal, operation| W
  P --> R[Review UI: accept / edit / reject<br/>per operation]
  R -->|review_operation| W
  R -->|commit_proposal| W
  W -->|entity, edge, assertion:<br/>one transaction, only after approval| KB
```

Nothing else writes. Intake and proposal storage record *what was said and what
is proposed* before review; only `commit_proposal` writes entity, edge and
assertion rows, and only after Álvaro has reviewed every operation. A database
write introduced anywhere outside `kb/apply.py` is a bug caught by the
`provenance-auditor` agent, the `kb-write-path` hook and an invariant test.

### What is written when (ADR-0009)

| Stage | Function in `kb/apply.py` | Writes |
|---|---|---|
| Intake | `record_source`, `record_evidence` | `source`, `evidence` (what was said, not what is true) |
| Proposal | `record_proposal` | `proposal`, `operation` (all `pending`) |
| Review | `review_operation` | one operation's status, plus `edited_payload_json` for an edit |
| Commit | `commit_proposal` | `entity`, kind tables, `edge`, `assertion`, `commit_log`, in one transaction |

A commit refuses while any operation is `pending`. It applies `accepted` and
`edited` operations, skips `rejected` ones, and rolls the whole proposal back if
any of them fails.

### The four classifications

`kb/classify.py` compares each candidate with stored rows. The model does not
decide this.

| Value | Means | Accepting it |
|---|---|---|
| `new` | Nothing stored covers it | Creates or changes rows |
| `known` | Already recorded (same kind and normalized name, field value or edge) | Adds evidence to the existing record |
| `duplicate` | A differently named record is probably the same thing, found by `kb/embeddings.py`'s `sqlite-vec` similarity index at or above the configured threshold (FR-05, ADR-0013) | Links to that record |
| `conflict` | Recorded with a different value | Replaces the value; the old assertion stays as history |

## Backup, export and migrations (NFR-09)

The knowledge base is one file, `data/cvforge.db`. It uses the default rollback
journal rather than WAL, so there are no `-wal` or `-shm` side files. To take a
portable, consistent copy, even while the app is running:

```sh
uv run python -m cvforge.kb.export /path/outside/the/repo/cvforge-copy.db
```

The copy opens with any SQLite tool, and restoring means putting it back at
`data/cvforge.db`. The command refuses to overwrite an existing file.

On startup, the app migrates the database to the newest Alembic revision. If a
migration is pending on an existing database, it first writes a copy to
`data/backups/cvforge-<revision>-<timestamp>.db`, where `<revision>` is the
revision the database was at *before* migrating. A brand-new file has nothing to
back up. A schema change is a new file
in `src/cvforge/kb/migrations/versions/`. `tests/integration/test_migrations.py`
fails if the migrated schema and `schema.py` disagree.

## Non-knowledge state

Not every table in the same file is knowledge. `app_setting` (the LLM provider
configuration, `cvforge.llm.settings_store`) carries no assertion, no evidence
and no provenance — it is one row of process configuration, not a fact about
Álvaro's career. It is written by `llm/settings_store.py`, a **registered
writer** (ADR-0011), never by `kb/apply.py`. The distinction matters for
`table_counts` and any tool that treats "everything in `cvforge.db`" as
knowledge: `app_setting` is deliberately outside that count.

`entity_vec` (a `sqlite-vec` `vec0` virtual table of entity name embeddings,
`cvforge.kb.embeddings`) is the same kind of non-knowledge state: it carries
no assertion or evidence either, only a derived vector per entity, and is
disposable — dropping it and re-running `reindex_missing` rebuilds it from the
entities that already exist. It is written by `kb/embeddings.py`, also a
registered writer, and rebuilt whenever the configured embedding dimension
changes (ADR-0013).
