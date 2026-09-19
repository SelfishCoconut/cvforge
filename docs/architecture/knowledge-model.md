# Knowledge model

```mermaid
erDiagram
  ENTITY ||--o{ EDGE : "src"
  ENTITY ||--o{ EDGE : "dst"
  SOURCE ||--o{ EVIDENCE : contains
  EVIDENCE ||--o{ ASSERTION : supports
  ASSERTION }o--|| ENTITY : "targets (target_kind=entity)"
  ASSERTION }o--|| EDGE : "targets (target_kind=edge)"
  PROPOSAL ||--o{ OPERATION : contains
  PROPOSAL }o--|| SOURCE : "derived from"

  ENTITY { string id string kind string name string normalized_name string state }
  EDGE { string id string src_id string rel string dst_id float confidence }
  SOURCE { string id string kind string uri string content_hash }
  EVIDENCE { string id string source_id string locator string excerpt }
  ASSERTION { string id string target_kind string target_id string field string evidence_id }
  PROPOSAL { string id string origin string status }
  OPERATION { string id int seq string op_type string classification string status }
```

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
  P --> R[Review UI: accept / edit / reject<br/>per operation]
  R --> W[kb/apply.py]
  W -->|one transaction| KB
```

Nothing else writes. A database write introduced anywhere outside `kb/apply.py`
is a bug caught by the `provenance-auditor` agent, the `kb-write-path` hook and an
invariant test.
