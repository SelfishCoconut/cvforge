# CVForge — system design

Date: 2026-09-12
Status: approved (sections 1–9); SRS formalization is an M0 deliverable
Author: Álvaro Navarro (decisions) · drafted with Claude Code

CVForge is a **local-first personal professional knowledge system**. It continuously
learns what Álvaro knows and has done, and uses that knowledge to analyze job
openings, generate tailored CVs, identify knowledge gaps, build learning plans,
prepare for interviews, and assist with application forms.

It is explicitly **not** an "AI CV generator". The CV is one output of a
knowledge base that is the source of truth.

---

## 1. Governing principles

1. **The database is the source of truth, not the LLM.** The LLM interprets and
   proposes; the database records. Every important fact traces to evidence.
2. **Nothing is stored without review.** The agent has no write access. Its only
   output is a proposal the user accepts, edits or rejects — per operation.
3. **Local-first.** Default backend is a local Ollama endpoint. External providers
   (Anthropic, OpenAI) and web search are opt-in, behind explicit interfaces.
4. **No fabrication.** Automatic CV generation emits no claim that lacks a stored
   assertion. This is enforced by a validator and by tests, not by prompt wording.
5. **Untrusted input stays data.** Fetched web pages, uploaded documents and job
   postings are content to be analyzed, never instructions to be followed.

## 2. Approved decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **FastAPI + React SPA in one uvicorn process** — API under `/api`, built SPA at `/` | The approve/edit/reject and diff-review flows are genuinely UI-shaped; mirrors the revalid pattern Álvaro already knows |
| D2 | **SQLite**: joined-table entity inheritance + generic `edge` table + `sqlite-vec` | Single file, zero services, trivial backup; recursive CTEs cover the graph queries; vectors for dedup and matching |
| D3 | **Changeset proposals** — agents emit `Proposal`/`operation` rows; `kb/apply.py` is the only writer | Makes "nothing stored without review" structural rather than prompt-dependent; one review UI serves chat, document and interview ingest |
| D4 | **Pydantic AI** agents; tools are read-only, output is plain data | Deterministic testability (`TestModel`/`FunctionModel`); no path from a model to a write |
| D5 | **Default model `ollama:qwen3.6:27b`**, runtime-switchable; env seeds settings on first run only | Strongest local model available; extraction quality determines KB trustworthiness |
| D6 | **Public repo** `SelfishCoconut/cvforge` | Full free security pipeline (CodeQL) + hosted docs site; requires absolute discipline that no personal data is ever committed |
| D7 | **MkDocs + mkdocstrings API pages; no auto-generated UML** | Published docs without the pyreverse layer-map maintenance burden that broke revalid CI |
| D8 | **ADRs kept** (`docs/adr/`, MADR) | They are the durable record of *why*, which is what survives context clearing |
| D9 | **No Kanban board automation**, no AI-usage declaration | Not needed outside the TFG regulation; issue-first + branches + PRs retained |
| D10 | **Regression guarantee = 90% line+branch coverage + golden E2E suite + `regression-guard` agent** | Coverage alone lets prompt/pipeline drift pass silently; golden snapshots make drift a visible diff |
| D11 | **CV artifacts: `.tex` + `.pdf` + plain-text ATS rendering** | The `.txt` is what ATS parsers read and what feeds the form-filling feature; diffs cleanly across versions |
| D12 | **Web access: httpx + trafilatura, Playwright fallback; optional pluggable `SearchProvider`** | JS-rendered boards need a real browser (same dependency as form filling); nothing leaves the machine without an opt-in key |
| D13 | **Form filling: Playwright with a dedicated persistent profile under `data/`, headed by default** | An LLM-driven process never touches the real Chrome profile; user watches every field; nothing auto-submits |
| D14 | **Frontend: React 19 + TypeScript + Vite + Tailwind v4 + headless primitives** | Room for distinctive design (avoids the shadcn "AI app" look) while keeping a11y on interactive primitives |

Not adopted, and why: direct agent writes with an undo journal (review becomes
after-the-fact); a staging database promoted on accept (complexity lands in the
read path); hosted scraping/search as the primary path (contradicts local-first);
driving the user's real Chrome (exposes the full logged-in identity to an
LLM-driven process).

## 3. Architecture

```
┌──────────────────────── one uvicorn process ────────────────────────┐
│  React SPA  (/)                     FastAPI  (/api)                 │
│  chat · review · jobs · match ·     routers → services              │
│  CV versions · settings · forms                                     │
├─────────────────────────────────────────────────────────────────────┤
│  llm/        Pydantic AI agents (read-only tools, structured out)   │
│  ingest/     document → text + evidence locators                    │
│  web/        fetch (httpx+trafilatura) · browser (Playwright) ·      │
│              search (pluggable, optional)                           │
│  match/      requirement ↔ knowledge verdicts                       │
│  cv/         render LaTeX · compile PDF · plain text · validate      │
│  forms/      field analysis · per-field options · assisted fill      │
├─────────────────────────────────────────────────────────────────────┤
│  kb/         queries.py (read) · apply.py (THE ONLY WRITER)          │
│              dedup.py · embeddings.py                               │
├─────────────────────────────────────────────────────────────────────┤
│  SQLite  cvforge.db  (entities · edges · provenance · proposals ·    │
│          jobs · matches · CVs · applications)  + sqlite-vec          │
└─────────────────────────────────────────────────────────────────────┘
          ↕ local Ollama (default)      ↕ Anthropic / OpenAI (opt-in)
```

Binds `127.0.0.1` only. No authentication — single-user local tool, by design.

## 4. Data model

### 4.1 Entities (joined-table inheritance — one id space, real foreign keys)

```
entity(id, kind, name, normalized_name, summary, state, first_seen_at, updated_at)
  ├─ skill(id→entity, category)            # language|framework|tool|platform|method|soft
  ├─ project(id→entity, started_at, ended_at, context)
  ├─ organization(id→entity, org_type, industry, size)   # employer|client|institution
  ├─ role(id→entity, title, seniority, started_at, ended_at, employment_type)
  ├─ education(id→entity, degree, field, started_at, ended_at, grade)
  ├─ credential(id→entity, credential_type, issuer, issued_at, expires_at,
  │             credential_id, url)        # certification|course|bootcamp
  ├─ achievement(id→entity, metric, value, occurred_at)
  └─ responsibility(id→entity, scope)
```

Deliberate collapses: a *technology* is a `skill` with a category (a separate kind
splits every query and buys nothing); *certification* and *course* are one
`credential` kind discriminated by `credential_type`.

No entity table carries a foreign key to another entity. An `education`'s
institution, a `role`'s employer and a `credential`'s issuing organization are all
`at_organization` **edges** — relationships live in exactly one place (§4.2), so
there is one way to traverse them and one way to evidence them.

### 4.2 Relationships

```
edge(id, src_id→entity, rel, dst_id→entity, confidence, started_at, ended_at, note)
UNIQUE(src_id, rel, dst_id)
```

`rel` is a **closed vocabulary**, never free text:
`used_in` · `at_organization` · `produced` · `involved` · `demonstrates` ·
`taught_by` · `part_of` · `related_to`.

"Python used in project X, project X for company Y, project X produced
achievement Z" is three edges. Multi-hop questions ("which skills have evidence
at company Y?") are recursive CTEs.

### 4.3 Provenance

```
source(id, kind, label, uri, content_hash, captured_at, raw_text_path)
        # kind: conversation | document | web | manual
evidence(id, source_id, locator, excerpt)
        # locator: page+char span, message id, DOM selector…
assertion(id, target_kind, target_id, field, value_json, evidence_id,
          confidence, created_at)
        # target_kind: entity | edge;  field NULL = existence of the thing itself
```

`assertion` answers "where did *managed a team of five* come from". **No entity
and no edge may exist without at least one assertion** — this is the structural
defense against gradual fact invention, checked by the `provenance-auditor` agent
and by an invariant test.

### 4.4 Knowledge state vs match verdict (two different axes)

`entity.state` ∈ `confirmed | learning | gap | archived`.

"Things I have but have not recorded" is deliberately **not** a state — by
definition such a thing is not in the database. It is a **match verdict**
(§4.6) that triggers a discovery question; answering it produces a proposal.

### 4.5 Review pipeline

```
proposal(id, origin, source_id, status, summary, created_at, applied_at)
        # origin: chat | document | interview | web
operation(id, proposal_id, seq, op_type, payload_json, classification,
          target_entity_id, conflict_with_id, status, edited_payload_json,
          rationale)
commit_log(id, proposal_id, applied_at, operation_ids_json)
```

- `op_type` ∈ `create_entity | update_field | add_edge | attach_evidence | merge_duplicate | set_state`
- `classification` ∈ `new | known | duplicate | conflict` (with the duplicate/conflicting target named)
- `status` ∈ `pending | accepted | edited | rejected | applied`

Commit applies `accepted` + `edited` operations in **one transaction**, writes the
entities/edges/assertions, and records a `commit_log` row. `kb/apply.py` is the
only module that writes these tables — enforced by test and by the
`kb-write-path` hook, not by convention.

### 4.6 Downstream tables (schema reserved now, built M3–M8)

```
job_posting(id, url, source_id, organization_id, title, seniority, location,
            work_model, raw_text, analysis_json, fetched_at)
requirement(id, job_posting_id, kind, text, normalized_skill_id)
            # kind: required | preferred | responsibility
match(id, job_posting_id, requirement_id, verdict, entity_id, score, rationale)
            # verdict: satisfied | evidenced | undocumented | gap
cv(id, job_posting_id, version, parent_cv_id, label, generation_mode,
   tex_path, pdf_path, txt_path, created_at)
cv_claim(id, cv_id, section, bullet_index, text, entity_id, assertion_id)
application(id, job_posting_id, cv_id, status, applied_at, notes)
form_fill_session(id, application_id, url, fields_json, status, created_at)
```

`cv_claim` is what makes claim-level traceability and CV validation possible, and
`application` is the job ↔ CV ↔ date linkage.

**The four verdicts, defined precisely** (they are ordered, and the boundaries must
not blur):

| Verdict | Means | Requires |
|---|---|---|
| `satisfied` | The requirement maps to a `confirmed` entity that is itself evidenced as *used* | A matching entity plus ≥1 `used_in` / `demonstrates` edge, each backed by an assertion |
| `evidenced` | Not directly recorded, but strongly implied by what is recorded | Supporting assertions on adjacent entities (e.g. a framework used implies its language), with the inference stated in `rationale` |
| `undocumented` | Plausibly true of Álvaro but absent from the knowledge base | No supporting entity; similarity to his recorded profile above threshold. Triggers a discovery question (FR-30), never a CV claim |
| `gap` | Genuinely absent | No entity, no supporting evidence, no plausible inference. Feeds the learning planner (FR-33) |

`undocumented` and `gap` may **never** produce a CV claim in automatic mode —
that is NFR-05 restated at the matching layer.

### 4.7 Semantic search

`sqlite-vec` virtual table over entity `name + summary` embeddings, produced by
an `EmbeddingProvider` interface (default `nomic-embed-text` via Ollama). Used for
duplicate-candidate retrieval and requirement↔skill matching. Tests inject
deterministic fake vectors; **CI never calls a model.**

## 5. Agent architecture

One hard rule: **agent tools are read-only; agent output is plain data.**

- `llm/provider.py` — `build_model()` reads a DB-persisted settings row
  (provider, model, base_url, api-key reference). Environment variables *seed*
  that row on first run only; thereafter the `/settings` view changes it at
  runtime with no restart.
- Agents, each with a structured output type:
  `IngestAgent` (text → `Proposal`) · `DocumentAgent` (document → `Proposal`) ·
  `JobAgent` (page text → `JobAnalysis`) · `MatchAgent` · `CVAgent`
  (facts → LaTeX sections) · `InterviewAgent` · `PlanAgent`.
- Available tools, all reads: `search_entities`, `get_entity`, `neighbours`,
  `find_similar`.
- Prompts live in `llm/prompts/` as files, so a prompt change is a reviewable diff
  covered by the golden suite.

## 6. Requirements catalogue (draft — formalized into `docs/requirements/srs.md` in M0)

IDs are immutable and never reused. Each FR gets a GitHub issue labelled
`req:FR-xx` and testable acceptance criteria.

**Knowledge base**
- FR-01 Store entities of the eight kinds in §4.1.
- FR-02 Store typed, optionally time-bounded relationships from the closed vocabulary.
- FR-03 Every entity field value and every edge traces to ≥1 assertion bound to an evidence span in a source.
- FR-04 Each entity carries a knowledge state (`confirmed|learning|gap|archived`).
- FR-05 Embedding-based similarity search over entities.
- FR-06 All mutations pass through the single write path; no agent has write access.

**Review pipeline**
- FR-07 Agents emit proposals of typed operations; they never write directly.
- FR-08 Each operation is classified `new|known|duplicate|conflict` with the related target identified.
- FR-09 Operations are reviewable independently: accept, edit, reject.
- FR-10 Accepted/edited operations commit atomically with assertions written and the commit logged.

**Conversational agent**
- FR-11 Free-text statement → proposal displayed before anything is stored.
- FR-12 Conversations persist as sources, so assertions can cite the exact message.
- FR-13 Streamed agent responses in the UI.

**Document ingestion**
- FR-14 Upload PDF, DOCX, Markdown and plain text.
- FR-15 Extract structured candidates with evidence locators (page + character span).
- FR-16 Detect duplicates and conflicts against the existing knowledge base.

**Job intake**
- FR-17 Fetch a job page by URL (static fetch, Playwright fallback for JS-rendered boards).
- FR-18 Produce a structured analysis: title, seniority, required skills, preferred skills, responsibilities, technologies, experience requirements, keywords, location, working model, other requirements.
- FR-19 Optional company research through a pluggable search provider (products, technologies, engineering practices, culture).
- FR-20 Persist the posting and decompose it into individual requirements.

**Matching**
- FR-21 Match each requirement against the knowledge base with verdict `satisfied | evidenced | undocumented | gap`.
- FR-22 Surface the supporting entities and evidence behind each verdict.
- FR-23 Produce a gap report for the posting.

**CV generation**
- FR-24 Automatic mode generates a CV strictly from stored facts.
- FR-25 Every CV claim links to the entity and assertion backing it.
- FR-26 Emit `.tex`, compiled `.pdf`, and a plain-text ATS rendering.
- FR-27 Version CVs with history and parent links.
- FR-28 Track which CV was generated for which job application, and when.
- FR-29 Validate a CV before presenting it: claim support, internal contradictions, date and technology consistency, coverage of the posting's important requirements.

**Collaborative mode**
- FR-30 Collaborative generation: the agent asks targeted discovery questions for plausible-but-unrecorded knowledge.
- FR-31 Conversational CV editing (emphasis, rewrite a bullet, shorten, shift technical/management focus) that still respects stored evidence.
- FR-32 Interview mode: directed elicitation of undocumented experience, converted to proposals for review.

**Learning**
- FR-33 Generate a learning plan for a gap: what to learn, how, which exercises or projects.
- FR-34 Track learning progress; a completed plan moves an entity from `learning` toward `confirmed`.

**Forms**
- FR-35 Analyze an application form and identify its fields.
- FR-36 Offer per-field value options with a prefilled default drawn from the knowledge base and the selected CV.
- FR-37 Fill fields on confirmation; never submit a form automatically.

**Providers and settings**
- FR-38 Pluggable LLM provider: Ollama (default), Anthropic, OpenAI.
- FR-39 Provider, model, base URL and key references persisted in the database and changeable at runtime.
- FR-40 Pluggable embedding provider.

**Non-functional**
- NFR-01 Local-first: no outbound network calls by default beyond the configured Ollama endpoint; external providers and search are opt-in.
- NFR-02 Binds `127.0.0.1` only; no authentication in scope (single user).
- NFR-03 ≥90% line **and** branch coverage on `src/`, enforced in CI.
- NFR-04 `mypy --strict` clean; xenon max-absolute complexity C.
- NFR-05 Automatic-mode CV generation emits zero claims lacking an assertion (validator- and test-enforced).
- NFR-06 Personal data is never committed: `data/`, `*.db`, `cv_out/` gitignored and hook-guarded.
- NFR-07 Fetched web content and uploaded documents are treated as untrusted data; they cannot influence tool use or database writes.
- NFR-08 No live model calls in unit, integration or golden tests.
- NFR-09 The knowledge base is one SQLite file; a documented export exists.
- NFR-10 Conversational proposal round-trip under 30 s p95 on `qwen3.6:27b` locally.

## 7. Milestones

| | Milestone | Delivers | Depends on |
|---|---|---|---|
| **M0** | Foundations | Public repo, CI/CD, 90% coverage gate, security pipeline, pre-commit, SRS, ADR-0001/0002, MkDocs site, `.claude` toolkit, FastAPI+SPA health skeleton | — |
| **M1** | Knowledge spine | Schema + provenance, LLM provider layer, conversational ingest agent, proposal→review→commit pipeline, chat + review UI | M0 |
| **M2** | Document ingestion | Upload → extract → classify new/known/duplicate/conflict → same review loop | M1 |
| **M3** | Job intake | URL → fetch → structured `JobPosting`; optional company research | M1 |
| **M4** | Match & gaps | Requirement ↔ knowledge matching, four verdicts, gap report | M1, M3 |
| **M5** | CV generation | Automatic mode, LaTeX → PDF + ATS text, claim traceability, versions, application linkage, validation | M4 |
| **M6** | Collaborative mode | Conversational CV editing, discovery questions, interview mode | M5 |
| **M7** | Learning plans | Gap → plan → tracked `learning` state | M4 |
| **M8** | Form autofill | Playwright persistent profile, per-field options with prefilled defaults, confirm-before-fill, never auto-submit | M5 |

## 8. Repository layout

```
src/cvforge/
  app.py config.py db.py
  models/      entity.py edge.py provenance.py proposal.py job.py cv.py
  schemas/     agent I/O + API types (Pydantic)
  kb/          queries.py apply.py dedup.py embeddings.py
  llm/         provider.py agents/ prompts/
  ingest/      documents.py chunking.py
  web/         fetch.py browser.py search.py
  match/       verdicts.py
  cv/          render.py compile.py to_text.py validate.py versions.py
  forms/       (M8)
  api/         routers
frontend/      React 19 + TS + Vite + Tailwind v4 + headless primitives
tests/         unit/ integration/ system/ golden/
docs/          requirements/srs.md  architecture/  adr/  guides/
scripts/demo/  one runnable demo per FR (the PR template's validation artifact)
templates/cv/  LaTeX templates
data/          gitignored — the real knowledge base, documents, browser profile
```

## 9. Toolchain, CI/CD and the regression guarantee

**Toolchain.** Python 3.12+ via `uv`; ruff (lint + format, line length 100, Google
docstrings); `mypy --strict` over `src`, `tests`, `scripts`; xenon complexity gate;
pytest with markers `integration`, `system`, `golden`; Node 22+ with Vite and
vitest; `latexmk`/`xelatex` for CV compilation (all present on this machine).

**`ci.yml` — every job required for merge:**
`quality` (ruff check + format, mypy strict, xenon) · `unit` (coverage
`fail_under=90`, branch coverage on) · `integration` · `golden` · `demos`
(every offline `make demo-*`) · `docs` (`mkdocs build --strict`) · `frontend`
(lint, typecheck, build, vitest coverage).

**`security.yml`:** pip-audit (with all extras exported), bandit, gitleaks over
full history, CodeQL for `python` **and** `javascript-typescript` in a single job
— a build matrix renames the check contexts and deadlocks branch protection, a
bug revalid hit and documented.

**`sanity.yml`** weekly: radon complexity trend, vulture dead code, pylint
duplicate-code, compared against the previous report in `docs/sanity/`.

**The three regression layers:**
1. **Coverage gate** — 90% line + branch on `src/`, hard failure. `--strict-markers`; no test may be skipped or xfailed without an issue reference.
2. **Golden suite** (`tests/golden/`) — recorded conversations, documents and job pages replayed through the real pipeline with deterministic Pydantic AI `FunctionModel` stand-ins, against committed snapshots. A prompt or pipeline tweak that silently changes extraction behaviour becomes a visible diff; `pytest --update-golden` regenerates, so reviewing that diff is the gate.
3. **`regression-guard` agent** — per-PR review for behaviour changed without a test, assertions weakened or deleted, new skips, and golden snapshots updated without justification.

**Workflow.** Issue first (labelled `req:FR-xx` / `infra` / `bug`, with a
milestone) → feature branch (`feat/fr-xx-slug`) → PR containing `Closes #n` and a
filled "How to validate" section → required CI green → squash merge. Conventional
Commits enforced by a commit-msg hook. Significant decisions get an ADR.

## 10. `.claude` toolkit

**Ported from the TFG repo, retuned** (thesis and Kanban language removed):
`requirements` · `feature-request` · `adr` · `docs` · `progress-report` · `run`;
agents `codebase-sanity` · `doc-curator`; hooks `remind-issue.sh` ·
`format-on-edit.sh`. Dropped entirely: `thesis`, `ai-declaration`, `retest-lab`,
`thesis-reviewer`, `log-ai-session.py`.

**New skills:** `kb-schema` (changing the knowledge schema without breaking the
single-write-path and assertion invariants — the repo's highest-risk area) ·
`llm-agent` (adding a Pydantic AI agent: structured output, read-only tools,
deterministic stand-ins) · `golden-tests` (record, review and update snapshots;
telling a regression from an intended change) · `cv-template` (LaTeX conventions,
compile path, traceability rules) · `release` (milestone close-out).

**New agents:** `regression-guard` (§9) · `provenance-auditor` (every entity and
edge has ≥1 assertion; no orphan evidence; no DB write outside `kb/apply.py`; no
agent tool that mutates).

**New hooks:** `guard-private-data.sh` — blocks any write or commit that would add
real career data (`data/`, `*.db`, `cv_out/`, CV-shaped files outside
`tests/data/`). revalid deliberately dropped its data guard; here it is
**necessary**: a public repo with real personal data on disk.
`kb-write-path.sh` — warns when an edit introduces a database write outside
`kb/apply.py`.

## 11. Claude Code plugins

**Enabled:** `superpowers` · `code-review` · `github` · `frontend-design` ·
`pydantic-ai` · `playwright` · `context7` · `commit-commands` · `pyright-lsp` ·
`semgrep` · `security-guidance` · `claude-md-management` · `code-simplifier` ·
`pr-review-toolkit` · `skill-creator`.

**For the clear-context-often workflow:** `remember` (continuous tiered session
memory) and optionally `session-report`. The already-configured `codebase-memory`
MCP covers structural code queries without bulk file reads.

**Known issue:** the `github` MCP server fails to connect — *"Authorization
header is badly formatted"*. The `gh` CLI works and is the fallback.

**Installed but not load-bearing:** `academic-research` (its skills are
paper/thesis-shaped; nothing in CVForge depends on it).

**Deliberately skipped:** `firecrawl`/`tavily`/`exa`/`brightdata`/`zyte` (hosted
scraping and search — contradicts local-first; a product-side search provider is
a runtime dependency, not a plugin) · `browser-use` (drives the real Chrome
profile) · `serena` (overlaps codebase-memory) · `qdrant`/`prisma`/`supabase`/
`data-engineering` (wrong stack) · `deepeval` (overlaps the golden suite) ·
`logfire`/`langfuse` (hosted by default — revisit at M5 if agent debugging
becomes painful).

## 12. Open questions

- **Anti-bot reality on Workday/Greenhouse (M8).** Some portals actively detect
  automation. The design degrades to the per-field suggestion list with manual
  entry, but whether full autofill works on the specific portals Álvaro targets
  is unknown until tested. Not a blocker for M0–M7.
- **Company research without a search key (M3).** With no `SearchProvider`
  configured the feature is URL-driven only. Whether that is acceptable, or a
  Brave/Tavily key gets added, is deferred to M3.
- **LaTeX CV template.** Whether to adopt an existing template or author one is
  deferred to M5; `templates/cv/` is reserved.
