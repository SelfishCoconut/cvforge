# CVForge — roadmap and current state

**Read this file first when resuming work.** It holds where the project stands,
what happens next, and the single next action. Keep it updated in the same PR
whenever milestone state changes.

Last updated: 2026-09-29

---

## Where we are

**Phase: M0 complete. M1 (knowledge spine) in progress — M1a (the storage half)
is merged (`1e19192`, PR #68); M1b (agent layer) and M1c (UI) are planned and
starting now.**

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

Executing `docs/superpowers/plans/2026-09-26-m1b-agent-layer.md`, package by
package, in this order: **B1** provider layer and settings (FR-38, FR-39, NFR-01,
NFR-02, NFR-08) → **B2** embeddings and `sqlite-vec` similarity (FR-40, FR-05) →
**B3** `record_proposal` classifying for itself (audit F2, first), then read-only
tools, `IngestAgent` and the chat endpoint (FR-06, FR-07, FR-11, FR-12) → **B4** streaming (FR-13, backend) → **B5** latency benchmark (NFR-10) →
**C1** the chat, review, knowledge and settings UI (FR-13, frontend). Each package
is one PR with `Closes #<n>` for the FR issues it delivers. The plan records the
decisions it takes (D-A to D-G) and the ADR each one gets.

**Package B1 is done (PR #72, on `feat/fr-38-provider-settings`), reviewed by
the three PR-review agents, and hardened once more against their combined
findings** (a knowledge-table guard on the writer registry independent of its
own derivation, the sqlite3-import bar actually applying to registered writers
as ADR-0011 says it should, the new CHECK constraints proven live against a
migrated database rather than only text-diffed, plus several smaller test
gaps). Awaiting merge.

**Package B2 — embeddings and `sqlite-vec` similarity search** (FR-40, FR-05;
closes #44, #9) is implemented on `feat/fr-40-embeddings` (2026-09-29): the full
gate is green; PR open and awaiting the three review agents. **Next: package B3**,
starting with B3.0 (`record_proposal` classifies for itself). B2 was executed natively
in-session, not subagent-driven: tasks stay small and sequential within a
package, and the project's own PR-review agents (`provenance-auditor`,
`regression-guard`, `doc-curator`) gate each package's PR, which is where
independent review adds the most value here.

Still open from the M1 tracker and not scheduled by that plan: #50
(`sync_issues.py`) and #53–#58 (CI and docs hygiene). NFR-07 (#46) is M2's.

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
| M1 | Knowledge spine | Schema + provenance, LLM provider layer, conversational ingest, proposal→review→commit, chat + review UI | in progress (M1a done; M1b, M1c planned) |
| M2 | Document ingestion | Upload → extract → classify new/known/duplicate/conflict → review | not started |
| M3 | Job intake | URL → fetch → structured `JobPosting`; optional company research | not started |
| M4 | Match & gaps | Requirement ↔ knowledge matching, four verdicts, gap report | not started |
| M5 | CV generation | LaTeX → PDF + ATS text, claim traceability, versions, application linkage, validation | not started |
| M6 | Collaborative mode | Conversational CV editing, discovery questions, interview mode | not started |
| M7 | Learning plans | Gap → plan → tracked `learning` state | not started |
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
