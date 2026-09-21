# CVForge — Software Requirements Specification

The authority on **what** CVForge must do. The design spec
(`docs/superpowers/specs/2026-09-12-cvforge-design.md`) is the authority on **how**.

**Rules**
- IDs are immutable and never reused. A new requirement takes the next free number.
- Every requirement is testable. If acceptance criteria cannot be phrased as
  something runnable or checkable, the requirement is split or rephrased.
- Every functional requirement maps 1:1 to a GitHub issue labelled `req:FR-xx`.
- Requirement changes are Álvaro's decisions: draft, confirm, then commit. A scope
  change also gets an ADR.

## Format

Each requirement below is a subsection with six fields, in this order:

1. Priority — MoSCoW: Must, Should, Could or Won't.
2. Milestone — which of M0–M8 delivers it.
3. Source — the design-spec section the requirement is drawn from.
4. Description — a single testable behaviour, phrased "The system shall …".
5. Acceptance criteria — a checklist of concrete, executable checks. Each
   positive check ("the system does X") is paired with its negative case ("and
   refuses rather than guessing when the precondition is absent"), because that
   negative half is what protects the invariants in design spec §1.
6. Traces to — the GitHub issue the requirement was filed as, and the test
   path(s) (or, for non-functional requirements, the config/workflow file) that
   enforce it.

## Knowledge base

### FR-01 — Store professional knowledge entities
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.1
- **Description**: The system shall store professional knowledge entities of the
  kinds `skill`, `project`, `organization`, `role`, `education`, `credential`,
  `achievement` and `responsibility`, each carrying a name, a normalized name, a
  summary and a knowledge state.
- **Acceptance criteria**:
  - [x] One entity of each of the eight kinds round-trips through the database with every common field preserved
  - [x] A kind outside the closed set is rejected before reaching the database
  - [x] `normalized_name` is derived deterministically (case-folded, whitespace-collapsed) and is queryable
- **Traces to**: issue #5, tests `tests/unit/test_entity_model.py`

### FR-02 — Store typed relationships between entities
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.2
- **Description**: The system shall store typed, optionally time-bounded
  relationships between entities as edges whose `rel` value is drawn from the
  closed vocabulary (`used_in`, `at_organization`, `produced`, `involved`,
  `demonstrates`, `taught_by`, `part_of`, `related_to`), unique per
  (source, relationship, destination).
- **Acceptance criteria**:
  - [x] An edge created with a closed-vocabulary `rel` and `started_at`/`ended_at` round-trips with all fields preserved
  - [x] An edge whose `rel` is outside the closed vocabulary is rejected before reaching the database
  - [x] Inserting a second edge with the same (`src_id`, `rel`, `dst_id`) violates the UNIQUE constraint rather than silently duplicating
  - [x] An edge with `ended_at` earlier than `started_at` is rejected rather than stored inconsistently
- **Traces to**: issue #6, tests `tests/unit/test_edge_model.py`

### FR-03 — Bind every fact to its evidence
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.3
- **Description**: The system shall record, for every entity field value and every
  edge, at least one assertion referencing an evidence span within a source, so
  that the origin of any stored fact can be displayed.
- **Acceptance criteria**:
  - [x] Committing an entity without at least one assertion raises and writes nothing
  - [x] Committing an edge without at least one assertion raises and writes nothing
  - [x] Given a stored fact, the API returns its source kind, locator and excerpt
  - [x] A repository-wide invariant test finds zero entities and zero edges lacking an assertion
- **Traces to**: issue #7, tests `tests/unit/test_provenance.py`, `tests/integration/test_invariants.py`

### FR-04 — Track a knowledge state per entity
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.4
- **Description**: The system shall carry a knowledge state on every entity, one
  of `confirmed | learning | gap | archived`, changeable only through an
  approved `set_state` operation.
- **Acceptance criteria**:
  - [x] Each of the four states round-trips and is filterable in a query
  - [x] A state value outside the closed set is rejected before reaching the database
  - [x] Changing an entity's state without a committed `set_state` operation is not possible through the write path
  - [x] "Something Álvaro has but never recorded" produces no entity — it surfaces only as a match verdict (§4.4), never as an implicit state
- **Traces to**: issue #8, tests `tests/unit/test_entity_model.py`

### FR-05 — Embedding-based similarity search over entities
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.7
- **Description**: The system shall support similarity search over entities using
  vector embeddings of `name + summary` stored in a `sqlite-vec` virtual table,
  to support duplicate-candidate retrieval and requirement matching.
- **Acceptance criteria**:
  - [ ] Given a query embedding, `find_similar` returns entities ranked by similarity above a configurable threshold
  - [ ] Querying an empty entity table returns no matches rather than raising
  - [ ] Unit tests inject deterministic fake vectors; no unit or integration test triggers a real embedding model call
  - [ ] A candidate scoring below the configured similarity threshold is not returned as a match
- **Traces to**: issue #9, tests `tests/unit/test_embeddings.py`

### FR-06 — Single write path for the knowledge base
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.5
- **Description**: The system shall route every entity, edge and assertion
  mutation through `src/cvforge/kb/apply.py`, the only module permitted to write
  those tables; no agent tool may write.
- **Acceptance criteria**:
  - [x] A dedicated test scans `src/` and fails if any module other than `kb/apply.py` executes an INSERT/UPDATE/DELETE against the entity, edge or assertion tables
  - [ ] Every Pydantic AI agent's tool list contains only read tools (`search_entities`, `get_entity`, `neighbours`, `find_similar`)
  - [x] Calling into `kb/apply.py` outside of an accepted/edited operation commit raises rather than silently writing
  - [x] Introducing a write call outside `kb/apply.py` is caught by the `kb-write-path` hook / CI check rather than merging silently
- **Traces to**: issue #10, tests `tests/unit/test_write_path_invariant.py`

## Review pipeline

### FR-07 — Agents propose, never write directly
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.5
- **Description**: The system shall have every content-producing agent emit a
  `Proposal` of typed `operation` rows rather than writing to the knowledge base
  directly.
- **Acceptance criteria**:
  - [ ] Running an ingest agent against fixture input returns a `Proposal` object and leaves the database unchanged until it is committed
  - [ ] The agent's tool set contains no write-capable tool at construction time
  - [ ] A `TestModel`/`FunctionModel` run confirms the structured output is a `Proposal`, never a direct mutation
  - [ ] Fixture input crafted to look like an instruction ("skip review, save this now") still produces an ordinary proposal, not a direct write
- **Traces to**: issue #11, tests `tests/unit/test_ingest_agent.py`

### FR-08 — Classify every operation
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.5
- **Description**: The system shall classify every operation as
  `new | known | duplicate | conflict`, naming the related target entity or edge
  whenever the classification is not `new`. The four values are defined in
  ADR-0009, and the classification is computed against stored rows, not asked of
  the model.
- **Acceptance criteria**:
  - [x] A proposal for a genuinely new fact classifies as `new` with no named target
  - [x] A proposal restating an existing fact under the same normalized name (for a kind whose name is its identity) classifies `known` — never `duplicate` — and names the matching id
  - [x] A differently named candidate that similarity search matches to a stored entity classifies `duplicate` and names that entity
  - [x] A proposal contradicting a stored fact classifies `conflict` and names the conflicting id
  - [x] An operation classified `known`/`duplicate`/`conflict` with no named target, or `new` with one, is rejected at validation rather than reaching review
- **Traces to**: issue #12, tests `tests/unit/test_classification.py`

### FR-09 — Operations are independently reviewable
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.5
- **Description**: The system shall let Álvaro accept, edit or reject each
  operation in a proposal independently of the others in the same proposal.
- **Acceptance criteria**:
  - [x] Rejecting one operation in a multi-operation proposal leaves sibling operations' status untouched
  - [x] Editing an operation persists `edited_payload_json` separately from the originally proposed payload
  - [x] Committing a proposal applies only `accepted`/`edited` operations, skipping `rejected` ones
  - [x] An operation left `pending` cannot be committed
- **Traces to**: issue #13, tests `tests/unit/test_review_pipeline.py`

### FR-10 — Commit atomically
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.5
- **Description**: The system shall commit all accepted and edited operations of
  a proposal in one transaction, writing the entities, edges and assertions and
  recording a `commit_log` row referencing the applied operation ids.
- **Acceptance criteria**:
  - [x] Committing a proposal with N accepted operations writes all N inside a single transaction
  - [x] A failure on the last operation of a batch rolls back the entire proposal rather than leaving earlier operations applied
  - [x] After commit, a `commit_log` row exists whose `operation_ids_json` matches exactly the applied operations
  - [x] Every entity/edge created by the commit has ≥1 assertion written in the same transaction — none is left without one
- **Traces to**: issue #14, tests `tests/integration/test_commit_pipeline.py`

## Conversational agent

### FR-11 — Free-text statement becomes a proposal
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §5
- **Description**: The system shall turn a free-text statement submitted in chat
  into a proposal displayed to Álvaro before anything is stored.
- **Acceptance criteria**:
  - [ ] Submitting a fixture sentence via the chat endpoint returns a `Proposal` and produces zero database writes
  - [ ] The proposal's operations cite the originating conversation `source` and message as evidence
  - [ ] A non-substantive message ("ok", "thanks") yields an empty proposal rather than fabricated content
  - [ ] The endpoint exposes no "apply directly" flag that bypasses review
- **Traces to**: issue #15, tests `tests/unit/test_ingest_chat.py`

### FR-12 — Conversations persist as citable sources
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.3
- **Description**: The system shall persist chat conversations as `source` rows
  (kind `conversation`) so that assertions can cite the exact message as
  evidence.
- **Acceptance criteria**:
  - [ ] Each chat message contributing to a proposal has a corresponding `source`/`evidence` row with a message-id locator
  - [x] Given a stored assertion originating from chat, the API resolves it back to the literal message text
  - [x] An operation with no source backing it is rejected before commit
  - [x] An assertion is never orphaned from a source — the foreign key is enforced, not just conventional
- **Traces to**: issue #16, tests `tests/unit/test_provenance.py`

### FR-13 — Stream agent responses
- **Priority**: Should
- **Milestone**: M1
- **Source**: design spec §6
- **Description**: The system shall stream agent responses to the chat UI
  incrementally rather than returning the full answer only once the model
  finishes.
- **Acceptance criteria**:
  - [ ] The chat endpoint under test returns a chunked/streamed response whose concatenated chunks equal the final message
  - [ ] A frontend test asserts the UI renders partial content as chunks arrive, not only on completion
  - [ ] A mid-stream interruption surfaces an error state rather than silently truncating with no indication
  - [ ] Streaming is exercised via a fake/`FunctionModel` streaming stand-in; no test opens a live model connection
- **Traces to**: issue #17, tests `tests/unit/test_chat_stream.py`, `frontend/src/**/*.test.tsx`

## Document ingestion

### FR-14 — Upload documents
- **Priority**: Must
- **Milestone**: M2
- **Source**: design spec §3
- **Description**: The system shall accept uploaded documents in PDF, DOCX,
  Markdown and plain-text formats for ingestion.
- **Acceptance criteria**:
  - [ ] Uploading a fixture of each of the four formats succeeds and extracts non-empty text
  - [ ] Uploading an unsupported format is rejected with a clear error before any extraction is attempted
  - [ ] A corrupted file with a supported extension fails extraction with a handled error rather than crashing the process
  - [ ] Uploaded bytes are stored under `data/` (gitignored), never inside the repository tree
- **Traces to**: issue #18, tests `tests/unit/test_document_upload.py`

### FR-15 — Extract candidates with evidence locators
- **Priority**: Must
- **Milestone**: M2
- **Source**: design spec §4.3
- **Description**: The system shall extract structured candidate facts from an
  uploaded document together with evidence locators (page number and character
  span) that pinpoint their origin.
- **Acceptance criteria**:
  - [ ] Each extracted candidate's locator, when sliced from the source text, reproduces the cited excerpt
  - [ ] A candidate with no resolvable locator is dropped rather than proposed without evidence
  - [ ] Extraction against a fixture with no extractable facts yields an empty proposal, not fabricated candidates
  - [ ] Re-running extraction over the same fixture yields locators that still resolve correctly
- **Traces to**: issue #19, tests `tests/unit/test_document_extraction.py`

### FR-16 — Detect duplicates and conflicts on ingest
- **Priority**: Must
- **Milestone**: M2
- **Source**: design spec §4.5
- **Description**: The system shall check extracted document candidates against
  the existing knowledge base and classify each as
  `new | known | duplicate | conflict` before review.
- **Acceptance criteria**:
  - [ ] A candidate identical to an existing entity/edge classifies `known`, naming the existing id; a differently worded candidate that similarity search matches classifies `duplicate`, naming it (ADR-0009)
  - [ ] A candidate contradicting a stored fact (e.g. conflicting employment dates) classifies `conflict`, naming the conflicting id
  - [ ] A wholly new candidate classifies `new`
  - [ ] Ingesting the same document twice does not create duplicate entities — the second run's candidates classify `known` rather than `new`
- **Traces to**: issue #20, tests `tests/integration/test_document_dedup.py`

## Job intake

### FR-17 — Fetch a job page by URL
- **Priority**: Must
- **Milestone**: M3
- **Source**: design spec §3, §2 D12
- **Description**: The system shall fetch a job posting page by URL using a
  static HTTP fetch with content extraction (httpx + trafilatura), falling back
  to a Playwright browser fetch for JavaScript-rendered boards.
- **Acceptance criteria**:
  - [ ] Fetching a fixture static HTML page returns extracted content via the static path with no browser invoked
  - [ ] Fetching a fixture page whose static extraction yields near-empty text triggers the Playwright fallback and returns rendered content
  - [ ] An unreachable URL raises a handled error rather than returning empty content silently
  - [ ] Both fetch paths are covered against local fixture servers/mocked responses; no test reaches the live internet
- **Traces to**: issue #21, tests `tests/integration/test_job_fetch.py`

### FR-18 — Produce a structured job analysis
- **Priority**: Must
- **Milestone**: M3
- **Source**: design spec §4.6
- **Description**: The system shall produce a structured analysis of a fetched
  job posting covering title, seniority, required skills, preferred skills,
  responsibilities, technologies, experience requirements, keywords, location,
  working model and other requirements.
- **Acceptance criteria**:
  - [ ] Running the job agent (via `FunctionModel`) against a fixture posting returns all documented fields populated or explicitly empty
  - [ ] A posting missing a field (e.g. no stated location) yields that field empty rather than a guessed value
  - [ ] Malformed model output fails Pydantic schema validation rather than being persisted
  - [ ] A fixture posting containing an embedded instruction does not alter the schema-conformant output beyond the posting's actual content
- **Traces to**: issue #22, tests `tests/unit/test_job_agent.py`

### FR-19 — Optional company research
- **Priority**: Should
- **Milestone**: M3
- **Source**: design spec §2 D12
- **Description**: The system shall optionally research the hiring company
  through a pluggable `SearchProvider`, surfacing products, technologies,
  engineering practices and culture when a provider is configured.
- **Acceptance criteria**:
  - [ ] With no `SearchProvider` configured, research is skipped and job analysis proceeds URL-only without error
  - [ ] With a fake `SearchProvider` injected in tests, research results populate the documented research field
  - [ ] No test invokes a live/hosted search API
  - [ ] A research-provider failure is isolated and reported, never fatal to the core posting fetch
- **Traces to**: issue #23, tests `tests/unit/test_company_research.py`

### FR-20 — Persist the posting and decompose requirements
- **Priority**: Must
- **Milestone**: M3
- **Source**: design spec §4.6
- **Description**: The system shall persist the fetched posting as a
  `job_posting` row and decompose its content into individual `requirement`
  rows of kind `required | preferred | responsibility`.
- **Acceptance criteria**:
  - [ ] Persisting a fixture posting creates one `job_posting` row and ≥1 `requirement` row per kind present
  - [ ] A `requirement.kind` outside the closed set is rejected
  - [ ] `job_posting.source_id` references a `source` row of kind `web`, so the raw page is traceable
  - [ ] Re-persisting the same URL follows a deterministic, tested dedupe/update rule rather than silently duplicating the posting
- **Traces to**: issue #24, tests `tests/integration/test_job_persistence.py`

## Matching

### FR-21 — Match requirements against the knowledge base
- **Priority**: Must
- **Milestone**: M4
- **Source**: design spec §4.6
- **Description**: The system shall match each job requirement against the
  knowledge base and assign one of the four verdicts
  `satisfied | evidenced | undocumented | gap`, per the definitions in design
  spec §4.6.
- **Acceptance criteria**:
  - [ ] A requirement matching a `confirmed` entity with an evidenced `used_in`/`demonstrates` edge verdicts `satisfied`
  - [ ] A requirement with only adjacent supporting evidence verdicts `evidenced`, with the inference stated in `rationale`
  - [ ] A plausible-but-unrecorded requirement verdicts `undocumented`, never `satisfied`
  - [ ] A requirement with no entity and no plausible inference verdicts `gap`; no requirement is left without a verdict
- **Traces to**: issue #25, tests `tests/unit/test_match_verdicts.py`

### FR-22 — Surface supporting entities and evidence
- **Priority**: Must
- **Milestone**: M4
- **Source**: design spec §4.6, §4.3
- **Description**: The system shall surface, for each match verdict, the
  supporting entities and the evidence backing them.
- **Acceptance criteria**:
  - [ ] A `satisfied`/`evidenced` match's response includes the backing entity id(s) and resolvable evidence (source kind, locator, excerpt)
  - [ ] An `undocumented`/`gap` match's response includes no fabricated supporting entity — the field is empty
  - [ ] Every entity id referenced in a match response is fetchable via `get_entity`
  - [ ] A match whose backing entity has since been archived is flagged rather than silently still cited as support
- **Traces to**: issue #26, tests `tests/unit/test_match_evidence.py`

### FR-23 — Produce a gap report
- **Priority**: Must
- **Milestone**: M4
- **Source**: design spec §4.6
- **Description**: The system shall produce a gap report for a job posting,
  listing its `undocumented` and `gap` requirements to feed the learning
  planner (FR-33).
- **Acceptance criteria**:
  - [ ] The report over a fixture posting with a known verdict mix returns exactly the `undocumented`+`gap` requirements
  - [ ] A posting where every requirement is `satisfied`/`evidenced` produces an empty gap report rather than an error
  - [ ] Running the report twice against unchanged data returns the same result
  - [ ] Each gap-report entry retains a link back to its `requirement` id
- **Traces to**: issue #27, tests `tests/unit/test_gap_report.py`

## CV generation

### FR-24 — Generate a CV from stored facts only
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §6, NFR-05
- **Description**: In automatic mode the system shall generate a CV exclusively
  from facts already stored in the knowledge base, inventing no skill, experience,
  responsibility, achievement or other claim.
- **Acceptance criteria**:
  - [ ] Every generated bullet has a `cv_claim` row linking it to an entity and an assertion
  - [ ] Generation against a knowledge base containing no match for a job requirement omits that requirement rather than inventing a claim
  - [ ] A requirement matched only as `undocumented` or `gap` never appears as a CV claim
  - [ ] `cv/validate.py` rejects a CV containing an unsupported claim, and the API refuses to mark it final
- **Traces to**: issue #28, tests `tests/unit/test_cv_validate.py`, `tests/golden/test_cv_generation.py`

### FR-25 — Claim-level traceability
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §4.6
- **Description**: The system shall link every generated CV claim (`cv_claim`)
  to the entity and the assertion that support it.
- **Acceptance criteria**:
  - [ ] Every `cv_claim` row for a generated CV has a non-null `entity_id` and `assertion_id`
  - [ ] Given a CV claim, the API resolves it to the exact stored fact and its evidence excerpt
  - [ ] A `cv_claim` insert with a null `assertion_id` is rejected at the write path
  - [ ] Archiving a claim's backing entity is caught by a consistency check rather than leaving a dangling claim unexamined
- **Traces to**: issue #29, tests `tests/unit/test_cv_claim.py`

### FR-26 — Emit LaTeX, PDF and ATS text
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §4.6, §2 D11
- **Description**: The system shall render a generated CV as LaTeX (`.tex`),
  compile it to PDF, and additionally produce a plain-text ATS rendering.
- **Acceptance criteria**:
  - [ ] Rendering a fixture claim set produces a `.tex` file that compiles to a non-empty `.pdf` via `latexmk`/`xelatex`
  - [ ] The plain-text rendering contains the same claims as the `.tex`/`.pdf`, with LaTeX markup stripped
  - [ ] A LaTeX compile failure is caught and reported rather than silently producing a corrupt PDF
  - [ ] All three artifacts are written under `cv_out/` (gitignored), never into the repository tree
- **Traces to**: issue #30, tests `tests/integration/test_cv_render.py`

### FR-27 — Version CVs with lineage
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §4.6
- **Description**: The system shall version generated CVs, recording history and
  parent links (`parent_cv_id`) so a CV's lineage is traceable.
- **Acceptance criteria**:
  - [ ] Generating a new CV from an edited prior version sets `parent_cv_id` to the prior id and increments `version`
  - [ ] A posting's first CV has `parent_cv_id = NULL` and `version = 1`
  - [ ] Walking `parent_cv_id` from any CV terminates at a root with no cycles
  - [ ] Listing a posting's CVs returns them ordered by version with lineage intact
- **Traces to**: issue #31, tests `tests/unit/test_cv_versions.py`

### FR-28 — Track CV-to-application linkage
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §4.6
- **Description**: The system shall track which CV was used for which job
  application and when, via the `application` table.
- **Acceptance criteria**:
  - [ ] Recording an application links a `job_posting_id` and `cv_id` with an `applied_at` timestamp
  - [ ] Querying a CV's usages returns every application it was used for
  - [ ] Creating an application referencing a non-existent CV id is rejected
  - [ ] An application's `status` is restricted to a documented closed set rather than free text
- **Traces to**: issue #32, tests `tests/unit/test_application_tracking.py`

### FR-29 — Validate a CV before presenting it
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §4.6, §8
- **Description**: The system shall validate a CV before presenting it: claim
  support, internal contradictions, date and technology consistency, and
  coverage of the posting's important requirements.
- **Acceptance criteria**:
  - [ ] `cv/validate.py` rejects a CV containing a bullet with no backing `cv_claim`
  - [ ] `cv/validate.py` flags an internal contradiction (e.g. overlapping full-time role dates) rather than presenting it silently
  - [ ] A CV omitting a `required`-kind requirement the candidate is `satisfied` on is flagged as incomplete coverage
  - [ ] Only a CV that passes every check can be marked `final` via the API
  - [ ] `cv/validate.py` flags a technology claim inconsistent with the backing entity's recorded period (e.g. a framework claimed for a role that predates its release)
- **Traces to**: issue #33, tests `tests/unit/test_cv_validate.py`

## Collaborative mode

### FR-30 — Ask discovery questions for plausible gaps
- **Priority**: Should
- **Milestone**: M6
- **Source**: design spec §4.4, §4.6
- **Description**: The system shall have the agent ask targeted discovery
  questions during collaborative generation when a match verdict is
  `undocumented`, to elicit plausible-but-unrecorded knowledge.
- **Acceptance criteria**:
  - [ ] An `undocumented` verdict produces a question referencing the specific requirement, not a generic prompt
  - [ ] Answering a discovery question produces a normal reviewable proposal, never a direct write
  - [ ] A `gap` verdict does not trigger a discovery question — it feeds the learning planner instead, keeping the two paths distinct
  - [ ] Declining to answer leaves the entity state unchanged; no entity is silently created
- **Traces to**: issue #34, tests `tests/unit/test_discovery_questions.py`

### FR-31 — Conversational CV editing
- **Priority**: Must
- **Milestone**: M6
- **Source**: design spec §6
- **Description**: The system shall allow conversational editing of a generated
  CV (emphasis changes, bullet rewrite, shortening, shifting technical/
  management focus) that still respects stored evidence.
- **Acceptance criteria**:
  - [ ] Requesting a reworded bullet changes its phrasing but preserves its `entity_id`/`assertion_id` link
  - [ ] Requesting emphasis on a skill with no backing assertion is refused/redirected rather than adding an unsupported bullet
  - [ ] Each edit produces a new CV version (FR-27) rather than mutating history in place
  - [ ] `cv/validate.py` re-runs after every conversational edit and blocks presenting an edit that fails validation
- **Traces to**: issue #35, tests `tests/unit/test_cv_chat_edit.py`

### FR-32 — Interview mode
- **Priority**: Should
- **Milestone**: M6
- **Source**: design spec §5
- **Description**: The system shall support an interview mode that directs
  elicitation of undocumented experience, converting answers into proposals for
  review.
- **Acceptance criteria**:
  - [ ] Running the interview agent (via `FunctionModel`) over a fixture transcript emits a `Proposal`, with the conversation persisted as a `source` of origin `interview`
  - [ ] No answer is written to the knowledge base without passing through the standard review/commit pipeline
  - [ ] A session with no substantive answers yields an empty or minimal proposal, not fabricated content
  - [ ] The interview's questions are demonstrably derived from the posting's `undocumented`/`gap` requirements, not generic
- **Traces to**: issue #36, tests `tests/unit/test_interview_agent.py`

## Learning

### FR-33 — Generate a learning plan for a gap
- **Priority**: Should
- **Milestone**: M7
- **Source**: design spec §5, §4.6
- **Description**: The system shall generate a learning plan for a knowledge
  gap: what to learn, how, and which exercises or projects to undertake.
- **Acceptance criteria**:
  - [ ] Running the plan agent against a fixture `gap` requirement returns concrete steps/resources, not free prose only
  - [ ] The plan references the gap requirement it was generated for, traceable back to the gap report (FR-23)
  - [ ] Generating a plan performs no entity/state write itself — it stays read-only, consistent with the single-write-path invariant
  - [ ] A requirement with a verdict other than `gap` does not produce a spurious learning plan
- **Traces to**: issue #37, tests `tests/unit/test_plan_agent.py`

### FR-34 — Track learning progress
- **Priority**: Could
- **Milestone**: M7
- **Source**: design spec §4.4
- **Description**: The system shall track progress against a learning plan,
  moving an entity's state from `learning` toward `confirmed` as the plan is
  completed.
- **Acceptance criteria**:
  - [ ] Marking a plan's steps complete transitions the linked entity's state via an approved `set_state` operation
  - [ ] A plan with incomplete steps produces no state-change operation
  - [ ] Progress tracking against an entity that was never recorded as `learning` raises rather than silently creating one
  - [ ] Completed-plan state changes go through the same review/commit pipeline as any other mutation (FR-06, FR-10)
- **Traces to**: issue #38, tests `tests/unit/test_learning_progress.py`

## Forms

### FR-35 — Analyze an application form's fields
- **Priority**: Should
- **Milestone**: M8
- **Source**: design spec §2 D13
- **Description**: The system shall analyze an application form on a target page
  and identify its fields, each with a label, an inferred type and a
  required/optional flag.
- **Acceptance criteria**:
  - [ ] Field analysis against a fixture form page returns every input with a label, inferred type and required flag
  - [ ] A field with no discoverable label is still surfaced with a placeholder identifier rather than dropped
  - [ ] Analysis against a page with no form returns an empty field list rather than raising
  - [ ] Field analysis runs against local fixture HTML/Playwright pages; no test targets a live third-party site
- **Traces to**: issue #39, tests `tests/integration/test_form_analysis.py`

### FR-36 — Per-field options with prefilled defaults
- **Priority**: Should
- **Milestone**: M8
- **Source**: design spec §4.6
- **Description**: The system shall offer per-field value options with a
  prefilled default drawn from the knowledge base and the selected CV.
- **Acceptance criteria**:
  - [ ] A field matching a known fact (e.g. years of experience) gets a default derived from stored data/the selected CV, not invented
  - [ ] A field with no matching knowledge-base fact offers no fabricated default — it is left blank or flagged for manual entry
  - [ ] Suggested options persist on `form_fill_session.fields_json` for review before fill
  - [ ] Changing the selected CV changes prefilled defaults that depend on CV content
- **Traces to**: issue #40, tests `tests/unit/test_form_field_options.py`

### FR-37 — Confirm before fill, never auto-submit
- **Priority**: Should
- **Milestone**: M8
- **Source**: design spec §2 D13
- **Description**: The system shall fill form fields only after Álvaro confirms
  each value, and shall never submit the form automatically.
- **Acceptance criteria**:
  - [ ] The fill routine writes only to fields explicitly confirmed in the session; unconfirmed fields are left untouched
  - [ ] A static/AST check finds no `forms/` code path invoking a submit action on a submit-typed element
  - [ ] A fixture form's submit-button state is asserted unchanged after a fill run
  - [ ] The Playwright session runs headed by default, so every fill is visible before Álvaro submits manually
- **Traces to**: issue #41, tests `tests/integration/test_form_fill.py`

## Providers and settings

### FR-38 — Pluggable LLM provider
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §5, §2 D5
- **Description**: The system shall support pluggable LLM providers — Ollama
  (default), Anthropic, OpenAI — behind a common interface.
- **Acceptance criteria**:
  - [ ] `build_model()` returns a working model handle for each of the three providers against fakes/mocks, with no live call
  - [ ] Switching the persisted provider setting changes which provider the next `build_model()` call targets, without a restart
  - [ ] An unsupported provider name is rejected with a clear error rather than silently defaulting
  - [ ] With no configuration at all, the system defaults to the local Ollama endpoint
- **Traces to**: issue #42, tests `tests/unit/test_llm_provider.py`

### FR-39 — Runtime-changeable provider settings
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §5
- **Description**: The system shall persist provider, model, base URL and
  API-key references in the database, seeded from environment variables on
  first run only, and changeable at runtime via the `/settings` view.
- **Acceptance criteria**:
  - [ ] On first run with env vars set, the settings row is seeded from them exactly once
  - [ ] Changing an env var after first run has no effect — the DB-persisted row remains authoritative
  - [ ] A settings update call changes the persisted row and immediately changes the provider used by the next agent call
  - [ ] An API key is stored as a reference, never returned in plaintext by a read endpoint
- **Traces to**: issue #43, tests `tests/unit/test_settings.py`

### FR-40 — Pluggable embedding provider
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §4.7
- **Description**: The system shall support a pluggable embedding provider
  (default `nomic-embed-text` via Ollama) behind an `EmbeddingProvider`
  interface.
- **Acceptance criteria**:
  - [ ] A fake `EmbeddingProvider` substituted in tests produces deterministic vectors of the expected dimension
  - [ ] A fake provider returning a different vector dimension is accepted without editing `kb/embeddings.py`, and a provider missing a protocol method fails at construction
  - [ ] No unit, integration or golden test calls a live embedding model
  - [ ] An embedding-provider failure is handled and surfaced to the caller rather than crashing the request
- **Traces to**: issue #44, tests `tests/unit/test_embedding_provider.py`

## Non-functional requirements

### NFR-01 — Local-first by default
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §1
- **Description**: The system shall make no outbound network calls by default
  beyond the configured local Ollama endpoint; external LLM providers and web
  search are opt-in.
- **Acceptance criteria**:
  - [ ] A network-call audit over the default configuration shows zero calls to non-local hosts
  - [ ] Enabling Anthropic/OpenAI/search requires an explicit opt-in setting; without it, calls to those providers are refused before being attempted
  - [ ] CI's unit/integration/golden suites run with non-local network access disabled and still pass, proving no hidden outbound dependency
  - [ ] `docs/` states the opt-in providers and how to enable each one
- **Traces to**: issue #59, tests `tests/unit/test_network_policy.py`

### NFR-02 — Localhost binding, no authentication
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §3
- **Description**: The system shall bind the web server to `127.0.0.1` only,
  with no authentication layer, reflecting its single-user local-tool design.
- **Acceptance criteria**:
  - [ ] Inspecting the bound socket at startup shows `127.0.0.1`, never `0.0.0.0` or a public interface
  - [ ] A simulated request from a non-localhost origin cannot reach the API in the default configuration
  - [ ] An API route inventory test confirms no login/session/token endpoint exists
  - [ ] Exposing a different bind address requires an explicit, documented override rather than a default
- **Traces to**: issue #60, tests `tests/integration/test_app_bind.py`

### NFR-03 — Test coverage floor
- **Priority**: Must
- **Milestone**: M0
- **Source**: design spec §9
- **Description**: The test suite shall cover at least 90% of lines and 90% of
  branches in `src/`, enforced automatically.
- **Acceptance criteria**:
  - [x] `fail_under = 90` and `branch = true` are set in `pyproject.toml`
  - [x] The CI unit job fails when coverage drops below the floor
  - [x] No test is skipped or xfailed without an issue reference in the skip reason
- **Traces to**: issue #1, `.github/workflows/ci.yml`

### NFR-04 — Static quality gates
- **Priority**: Must
- **Milestone**: M0
- **Source**: design spec §9
- **Description**: The codebase shall pass `mypy --strict` over `src`, `tests`
  and `scripts`, and stay under xenon max-absolute complexity grade C for every
  function.
- **Acceptance criteria**:
  - [x] `mypy --strict src tests scripts` exits 0 in CI
  - [x] The xenon complexity check exits 0 in CI at max-absolute grade C
  - [x] A function introduced above grade C fails the CI `quality` job rather than merging
  - [x] A type error anywhere in `src`, `tests` or `scripts` fails CI rather than surfacing only at runtime
- **Traces to**: issue #1, `.github/workflows/ci.yml`

### NFR-05 — Zero unsupported claims in automatic mode
- **Priority**: Must
- **Milestone**: M5
- **Source**: design spec §1, §4.6
- **Description**: Automatic-mode CV generation shall emit zero claims lacking a
  stored assertion, enforced by the validator and by tests rather than by
  prompt wording.
- **Acceptance criteria**:
  - [ ] `cv/validate.py` rejects any CV containing a bullet without a linked `cv_claim`/assertion
  - [ ] A golden test feeds a knowledge base with deliberately sparse coverage and asserts the generated CV contains no claim beyond what is stored
  - [ ] A `FunctionModel` designed to try to hallucinate a claim is caught and blocked by the validator before presentation
  - [ ] The "mark CV final" API action refuses when validation has not passed
- **Traces to**: issue #45, tests `tests/unit/test_cv_validate.py`, `tests/golden/test_cv_generation.py`

### NFR-06 — Personal data is never committed
- **Priority**: Must
- **Milestone**: M0
- **Source**: design spec §10
- **Description**: Personal data shall never be committed to the repository:
  `data/`, `*.db` and `cv_out/` are gitignored, and a `guard-private-data` hook
  blocks writes or commits that would add real career data anyway.
- **Acceptance criteria**:
  - [x] `.gitignore` contains `data/`, `*.db` and `cv_out/`
  - [x] Staging a file under `data/`, or a CV-shaped file outside `tests/data/`, is blocked by the `guard-private-data` hook with a PreToolUse `deny` decision
  - [ ] A full-history secret/data scan finds no real personal data across repository history
  - [x] Every fixture under `tests/` is synthetic; none is a real CV, job posting or knowledge-base export
- **Traces to**: issue #1, `.github/workflows/security.yml`, `.claude/hooks/guard_private_data.py`; open criterion 3 tracked in issue #64

### NFR-07 — Untrusted external content
- **Priority**: Must
- **Milestone**: M2
- **Source**: design spec §1
- **Description**: Fetched web content and uploaded documents shall be treated
  as untrusted data: analyzed for facts, never obeyed as instructions, and
  unable to influence tool use or database writes.
- **Acceptance criteria**:
  - [ ] A fixture job posting/document containing an embedded instruction produces a normal proposal about the posting's actual content, with no altered tool call and no write
  - [ ] The read-only tool set available during job/document analysis stays fixed regardless of page content
  - [ ] The prompt-injection fixture is part of the golden suite, so a regression that starts obeying embedded instructions shows as a snapshot diff
  - [ ] Extracted facts from untrusted content still pass through the standard classify → review → commit pipeline; none bypass it
- **Traces to**: issue #46, tests `tests/golden/test_prompt_injection.py`

### NFR-08 — No live model calls in tests
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §9, §4.7
- **Description**: Unit, integration and golden tests shall never call a live
  LLM or embedding model; all model-shaped behaviour is exercised via Pydantic
  AI `TestModel`/`FunctionModel` or fake providers.
- **Acceptance criteria**:
  - [ ] CI runs the unit/integration/golden suites with network access to model endpoints disabled, and all pass
  - [ ] A check finds no live `ollama`/`anthropic`/`openai` client instantiation reachable from `tests/unit`, `tests/integration` or `tests/golden`
  - [ ] Every agent test constructs its agent with `TestModel` or a `FunctionModel` stand-in, never the real provider
  - [ ] Introducing a live call in a test is caught by that check and fails CI rather than silently incurring cost or latency
- **Traces to**: issue #61, `tests/conftest.py`, `.github/workflows/ci.yml`

### NFR-09 — Single-file database with a documented export
- **Priority**: Must
- **Milestone**: M1
- **Source**: design spec §2 D2
- **Description**: The knowledge base shall live in one SQLite file, with a
  documented export procedure so the data is portable and inspectable outside
  the app.
- **Acceptance criteria**:
  - [x] The running app writes to exactly one `.db` file path, confirmed by inspecting open connections during a test run
  - [x] A documented export command produces a portable copy that a test can load in a fresh location
  - [x] The export procedure is documented in `docs/` with the exact command
  - [x] Restoring from an exported copy reproduces the same entity/edge/assertion counts as the source
- **Traces to**: issue #62, tests `tests/integration/test_db_export.py`

### NFR-10 — Conversational proposal latency
- **Priority**: Should
- **Milestone**: M1
- **Source**: design spec §6, §2 D5
- **Description**: The conversational proposal round-trip (message submitted to
  proposal returned) shall complete under 30 seconds p95 on `qwen3.6:27b`
  running locally.
- **Acceptance criteria**:
  - [ ] A latency benchmark script records p95 round-trip time over a fixture set of representative messages against the local Ollama endpoint
  - [ ] The benchmark reports p95 under 30 s in the target environment; a regression above threshold is flagged in the weekly sanity report
  - [ ] The measurement excludes calls to opt-in external providers, which carry no latency SLA here
  - [ ] Unit/integration/golden tests do not assert on this latency directly — per NFR-08 they use fakes; the check is a separate, real-model benchmark
- **Traces to**: issue #47, `scripts/bench/latency.py`, `docs/sanity/`
