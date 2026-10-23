# CVForge — roadmap and current state

**Read this file first when resuming work.** It holds where the project stands,
what happens next, and the single next action. Keep it updated in the same PR
whenever milestone state changes.

Last updated: 2026-10-21 (M1 and M2 closed)

---

## Where we are

**Phase: M0, M1 (knowledge spine) and M2 (document ingestion) are complete and merged; released as `v0.3.0`. M3 (job intake) is next.**

Done:
- Design spec approved: `docs/superpowers/specs/2026-09-12-cvforge-design.md`.
- M0 plan executed: `docs/superpowers/plans/2026-09-12-m0-foundations.md`.
- Public repo `SelfishCoconut/cvforge`; `main` protected behind eleven required
  CI contexts, strict (branch must be up to date), linear history, no force
  pushes or deletions, conversation resolution required, **admins included**.
  Squash-only merges; branches deleted on merge. No required reviews (a solo
  author cannot approve their own PR). Tags are not protected — the `release`
  skill tags the merged commit.
- Toolchain: uv + Python 3.13, ruff, mypy --strict, xenon, pytest with a 90%
  line+branch coverage floor, pre-commit with Conventional Commits and gitleaks.
- Walking skeleton: `make build-ui && make run` serves the React SPA at
  http://127.0.0.1:8000 with `/api/health` live from the same process.
- Golden-snapshot harness, with the OpenAPI schema as its first gate.
- CI (7 jobs), security (pip-audit, Bandit, Gitleaks, CodeQL), weekly sanity
  metrics, Dependabot, issue and PR templates.
- SRS with FR-01..FR-40 and NFR-01..NFR-10, one GitHub issue per requirement.
- ADR-0001..0012 (see `docs/adr/README.md`). Released as `v0.1.0`. ADR-0008 to
  ADR-0012 were decided by Claude under Álvaro's delegation and are awaiting his
  confirmation (0010, 0011 and 0012 are marked `proposed`).
- **M1a — knowledge store and review pipeline (PR #68):** SQLite schema with
  provenance (SQLAlchemy Core + Alembic), `kb/apply.py` as the single writer,
  the deterministic classifier (`new | known | duplicate | conflict`), read
  queries, the review/commit API, the NFR-09 export, and the write-path invariant
  test. No model is involved yet. Closed #5–#8, #12–#14, #48, #62, #69; #10 and
  #16 are partial (agent tools and chat intake are M1b).
- **M1a review pass:** the three PR-review agents found and fixed, on the same
  PR: review/commit not serialised against concurrent requests (`BEGIN
  IMMEDIATE`), an accepted edge conflict silently nulling unstated columns, a
  test suite that opened the real `data/cvforge.db`, an invariant-2 scanner that
  missed most write idioms, and a pre-commit ruff pinned behind the locked one
  (#69). ADR-0010 records the storage/gate policies this surfaced. Deliberately
  deferred to M1b, because unreachable until it lands: `record_proposal` trusts
  the caller's classification (plan task B3.0, first in that package) and the
  API has no Host/Origin check (task B1.4).
- **M1b package B1 — pluggable LLM provider and runtime settings (PR #72):**
  `Provider` (ollama/anthropic/openai) in `kb/vocab.py`; the `app_setting`
  table (migration 0002) plus two evidence CHECK constraints (audit F5);
  `llm/settings_store.py` (`ProviderSettings`, `load_settings`/`save_settings`,
  the first real entry in the ADR-0011 registered-writer registry) and
  `llm/provider.py` (`build_model()` — Ollama needs no opt-in, Anthropic/OpenAI
  are refused before any client is constructed without `allow_external`);
  `GET`/`PUT /api/settings`; `api/security.py` closing the Host/Origin gap
  binding alone leaves (audit F6), since Starlette's own `TrustedHostMiddleware`
  mis-parses an IPv6 Host header. ADR-0011 and ADR-0012 record the two
  decisions this took. Closed #42, #43, #59, #60, #61.
- MkDocs site with mkdocstrings API pages and authored C4/ER/flow diagrams.
- `.claude` toolkit: 11 skills, 4 agents, 4 hooks, plugin set enabled
  (Semgrep deliberately dropped). The two gating hooks are Python files that
  **fail open** — a hook that errors blocks every tool call in the repo.

## Next action

**M8 — form autofill (FR-35..FR-37; issues #39-#41), the last milestone.** FR-35 is merged (#168).
FR-36 and FR-37 are PR #169 (suggestions from the selected CV, `form_fill_session`, `forms/fill.py`:
confirmed fields only, headed persistent profile, never submits, pinned by an AST test; the
`/api/forms/fills` routes and the `/forms` page). **Remaining for M8:** merge #169, then the
`release` skill. Form pages are untrusted data (NFR-07): analyse, never obey. Known follow-up: the
fill route has no atomic claim of the session, so a retried request can fill twice.

M7 closed as `v0.8.0` (2026-10-21): FR-33 learning plans for `gap` requirements and FR-34 progress
tracking whose completion only proposes a `set_state` (ADR-0029). Sanity audit
`docs/sanity/2026-10-21-m7.md`: WATCH, no must-fix; its items were fixed in the close PR.

Loose ends: #145 (flaky `test_document_dedup`, now in M8); no UI for anything built in M3-M7 (the whole
API is headless: jobs, matches, CVs, applications, discovery, editing, plans); the reword grounding is
lexical (ADR-0028); `api/cvs.py` is 550+ lines; one failure-handling convention for the four
model-calling routers; evidence-span record in four places; "data, never instructions" prompt wording
in seven prompts; `llm/agents/cv_edit.py` imports `cv.store`; `persist_posting` can leave an orphan `web`
source; no concrete `SearchProvider`; NFR-10 on the default model needs the native Ollama adapter (#129);
#64 awaits Álvaro; ADRs 0010-0012 and 0015-0029 await his confirmation.

Close-out scope calls (M1/M2): #107 closed as delivered; #73, #64 and #58 left M1 (not
deliverables: #73 is the reference for two environment-dependent skips, #64 awaits Álvaro,
#58 is draft PR #91); #46 moved to M3. NFR-10 on the default reasoning model still fails
(p95 241.9 s vs 30 s); the native Ollama adapter (#129) is the real fix.

The text below is the historical M1/M2 log, kept for context.

Executing `docs/superpowers/plans/2026-09-26-m1b-agent-layer.md`, package by
package, in this order: **B1** provider layer and settings (FR-38, FR-39, NFR-01,
NFR-02, NFR-08) → **B2** embeddings and `sqlite-vec` similarity (FR-40, FR-05) →
**B3** `record_proposal` classifying for itself (audit F2, first), then read-only
tools, `IngestAgent` and the chat endpoint (FR-06, FR-07, FR-11, FR-12) → **B4** streaming (FR-13, backend) → **B5** latency benchmark (NFR-10) →
**C1** the chat, review, knowledge and settings UI (FR-13, frontend). Each package
is one PR with `Closes #<n>` for the FR issues it delivers. The plan records the
decisions it takes (D-A to D-G) and the ADR each one gets.

**Package B1 is done (PR #72, merged), reviewed by
the three PR-review agents, and hardened once more against their combined
findings** (a knowledge-table guard on the writer registry independent of its
own derivation, the sqlite3-import bar actually applying to registered writers
as ADR-0011 says it should, the new CHECK constraints proven live against a
migrated database rather than only text-diffed, plus several smaller test
gaps). Merged.

**Package B2 — embeddings and `sqlite-vec` similarity search** (FR-40, FR-05;
closes #44, #9) is **merged** (PR #74, `30d651b`, 2026-10-01): `EmbeddingProvider`,
the `entity_vec` index, post-commit indexing that never fails a commit
(`index_pending`), startup re-indexing, and a real `SimilarFinder` behind
`kb.classify`'s first genuine `duplicate`. ADR-0013 part 1 is `proposed`. The
PR also bumped `urllib3`/`virtualenv` to clear new pip-audit advisories.

**M1b backend is merged (2026-10-05).** B3 — `record_proposal` classifying for
itself, `kb/intake.propose`, the fact schema and converter, the read-only tools and
`IngestAgent`, `POST /api/chat/messages`, the golden replay, `make demo-chat-ingest`,
ADR-0013 part 2 — is PR #79. B4 — NDJSON streaming, `POST /api/chat/messages/stream`,
ADR-0014 — is PR #82 (it replaced #80, which GitHub auto-closed when #79's branch was
deleted). B5 — the real-model latency benchmark, NFR-10 — is PR #81, closing #47. The
benchmark ships as a tool; its first recorded run is `docs/sanity/2026-10-19-nfr10-latency.md`
(instruct model p95 8.0 s; the default reasoning model fails on the token limit, #123).
**C1 is merged** (the stack ending at #106): the chat, review, knowledge and settings views, the
ADR-0015 frontend foundation (`proposed`), `make demo-ui` / `make demo-ui-check` and
`tests/system/test_ui_loop.py`. The NFR-10 benchmark fix is PR #122 (merged).
**#123 was mis-diagnosed:** the default reasoning model fails because Ollama loads it with a
4096-token context window and its `/v1` endpoint ignores `options.num_ctx`, not because of
`max_tokens`. PR #124 makes the 502 name the cause and documents `OLLAMA_CONTEXT_LENGTH`
(`docs/guides/providers.md`). A native `/api/chat` adapter with a `num_ctx` setting is the
real fix and needs an ADR. **Next action:** merge #126 (certifi, clears a pip-audit
advisory) then #124; record the NFR-10 run on the default model with
`OLLAMA_CONTEXT_LENGTH=16384`; then close M1 via the `release` skill.
**M2 (document ingestion) backend is done, as stacked branches pushed but not merged:**
FR-14 upload and text extraction (PR #132, `feat/fr-14-document-upload`, ADR-0016) →
FR-15 cited-fact extraction (`feat/fr-15-document-extraction`, ADR-0017) → FR-16
(`feat/fr-16-document-dedup`, ADR-0018) → UI. FR-16 surfaced a real M1 bug: an edge between
entities that classified `known` was classified `new` and then violated the edge's unique
key at commit, refusing the whole proposal; `classify` and the commit-time check now resolve
`OpRef` ends (ADR-0018). Open each PR against `main` only after the one below it merges
(a PR whose base branch is deleted is auto-closed). The UI (`feat/m2-documents-ui`, #133) is the top of the stack and
is browser-unverified (no Chrome for Playwright on this machine; vitest, the HTTP loop and
`make demo-ui` pass). **Remaining for M2:** NFR-07 (#46) verification and the milestone close-out. Before pushing
a route or an ADR run `make docs`, `make ui-gen` (regenerate `schema.d.ts`) and the other
CI equivalents; the first push of #132 failed on exactly those.

Known gap, not scheduled: the write-path scanner does not cover DDL.

**M1 infra backlog cleared (2026-10-05):** `mkdocs<2` ceiling (#57), Dependabot npm
majors individually (#53), CI hygiene (#54), nightly `pytest -m system` workflow (#56;
`tests/system/` gains its first test with PR6), vitest 3.x with one vite major (#55), and
`scripts/sync_issues.py` (#50; `--check` is green, run it after every SRS edit).
Dependabot PR #71 (13 bundled majors, frontend branch coverage 80% < 90%) was
cancelled in favour of individual major bumps. Dependency bumps merged: uvicorn,
fastapi, pydantic-ai ≥2.52, SQLAlchemy 2.1.

Still open from M1: #58 is a **draft PR (#91)** awaiting Álvaro's confirmation of the
SRS wording changes; #73 stays open on purpose as the reference for the two
environment-dependent skips in `test_app_bind.py` (never observed to fire). The M2–M8
requirement issues (#18–#41, #45, #46) stay open as the backlog; NFR-07 (#46) is M2's.

One decision is waiting on Álvaro: #64, the personal email address in public git
history. It is deliberately left alone — rewriting public history is not
reversible.

**The issue-first rule is now in force.** Every change starts from a GitHub issue,
goes through a branch and a PR containing `Closes #<n>`, and merges only on green
CI. Direct pushes to `main` are rejected, including for admins.

## Milestones

| | Milestone | Delivers | Status |
|---|---|---|---|
| M0 | Foundations | Repo, CI/CD, coverage gate, security pipeline, SRS, ADRs, docs site, `.claude` toolkit, health skeleton | done |
| M1 | Knowledge spine | Schema + provenance, LLM provider layer, conversational ingest, proposal→review→commit, chat + review UI | done (`v0.3.0`) |
| M2 | Document ingestion | Upload → extract → classify new/known/duplicate/conflict → review | done (`v0.3.0`) |
| M3 | Job intake | URL → fetch → structured `JobPosting`; optional company research | done (`v0.4.0`) |
| M4 | Match & gaps | Requirement ↔ knowledge matching, four verdicts, gap report | done (`v0.5.0`) |
| M5 | CV generation | LaTeX → PDF + ATS text, claim traceability, versions, application linkage, validation | done (`v0.6.0`) |
| M6 | Collaborative mode | Conversational CV editing, discovery questions, interview mode | done (`v0.7.0`) |
| M7 | Learning plans | Gap → plan → tracked `learning` state | done (`v0.8.0`) |
| M8 | Form autofill | Playwright persistent profile, per-field options, confirm before fill | not started |

## Environment facts (verified 2026-09-12)

- `uv` 0.12.9 · Node v26.8.1 · `latexmk`, `xelatex`, `pdflatex` all present.
- Ollama 0.33.2 with `qwen3.6:27b`, `qwen3:14b`, `qwen3.5:9b` and
  `nomic-embed-text` pulled (re-verified 2026-09-26).
- Python 3.13.15 / SQLite 3.53.1: `sqlite3` supports `enable_load_extension`, so
  `sqlite-vec` can load (checked 2026-09-26; CI's build is proven by B2's first run).
- `gh` authenticated as `SelfishCoconut`; token scopes `gist, read:org,
  read:project, repo, workflow`. No `project` write scope — irrelevant, no board.
- The `github` MCP server still fails to connect (*Authorization header is badly
  formatted*, re-checked 2026-09-26). Use the `gh` CLI until it is fixed.

## Decisions that are settled — do not relitigate

See spec §2 for the full table with rationale. In brief: FastAPI + React SPA in
one process · SQLite with joined-table entity inheritance + generic edge table +
sqlite-vec · changeset proposals with `kb/apply.py` as the only writer · Pydantic
AI with read-only tools · default `ollama:qwen3.6:27b` · public repo · MkDocs
without UML · ADRs kept · no Kanban, no AI-usage declaration · 90% coverage +
golden suite + `regression-guard` · CV as `.tex` + `.pdf` + `.txt` · Playwright
with a dedicated profile · React 19 + Tailwind v4 + headless primitives ·
SQLAlchemy Core + Alembic, no ORM session (ADR-0006) · Material-native Mermaid,
no network at docs build time (ADR-0007).
