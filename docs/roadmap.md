# CVForge — roadmap and current state

**Read this file first when resuming work.** It holds where the project stands,
what happens next, and the single next action. Keep it updated in the same PR
whenever milestone state changes.

Last updated: 2026-09-21

---

## Where we are

**Phase: M0 complete. M1 (knowledge spine) is next.**

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
- ADR-0001..0007 (see `docs/adr/README.md`).
- MkDocs site with mkdocstrings API pages and authored C4/ER/flow diagrams.
- `.claude` toolkit: 11 skills, 4 agents, 4 hooks, plugin set enabled
  (Semgrep deliberately dropped). The two gating hooks are Python files that
  **fail open** — a hook that errors blocks every tool call in the repo.

## Next action

Write the M1 implementation plan (`superpowers:writing-plans`) covering FR-01 to
FR-13 and FR-38 to FR-40: the SQLite schema with provenance (SQLAlchemy Core +
Alembic per ADR-0006), the LLM provider layer, the conversational ingest agent,
the proposal → review → commit pipeline, and the chat + review UI. Open M1
issues already on the tracker (#47, #48, #50) feed into it.

**The issue-first rule is now in force.** Every change starts from a GitHub issue,
goes through a branch and a PR containing `Closes #<n>`, and merges only on green
CI. Direct pushes to `main` are rejected, including for admins.

## Milestones

| | Milestone | Delivers | Status |
|---|---|---|---|
| M0 | Foundations | Repo, CI/CD, coverage gate, security pipeline, SRS, ADRs, docs site, `.claude` toolkit, health skeleton | done |
| M1 | Knowledge spine | Schema + provenance, LLM provider layer, conversational ingest, proposal→review→commit, chat + review UI | not started |
| M2 | Document ingestion | Upload → extract → classify new/known/duplicate/conflict → review | not started |
| M3 | Job intake | URL → fetch → structured `JobPosting`; optional company research | not started |
| M4 | Match & gaps | Requirement ↔ knowledge matching, four verdicts, gap report | not started |
| M5 | CV generation | LaTeX → PDF + ATS text, claim traceability, versions, application linkage, validation | not started |
| M6 | Collaborative mode | Conversational CV editing, discovery questions, interview mode | not started |
| M7 | Learning plans | Gap → plan → tracked `learning` state | not started |
| M8 | Form autofill | Playwright persistent profile, per-field options, confirm before fill | not started |

## Environment facts (verified 2026-09-12)

- `uv` 0.12.9 · Node v26.8.1 · `latexmk`, `xelatex`, `pdflatex` all present.
- Ollama 0.33.2 with `qwen3.6:27b`, `qwen3:14b`, `qwen3.5:9b` pulled.
  **`nomic-embed-text` is NOT pulled yet** — needed for semantic dedup (M1):
  `ollama pull nomic-embed-text`.
- `gh` authenticated as `SelfishCoconut`; token scopes `gist, read:org,
  read:project, repo, workflow`. No `project` write scope — irrelevant, no board.
- The `github` MCP server currently fails to connect (*Authorization header is
  badly formatted*). Use the `gh` CLI until it is fixed.

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
