# CVForge — roadmap and current state

**Read this file first when resuming work.** It holds where the project stands,
what happens next, and the single next action. Keep it updated in the same PR
whenever milestone state changes.

Last updated: 2026-09-12

---

## Where we are

**Phase: design approved, nothing implemented yet.**

Done:
- Requirements and architecture brainstormed and approved by Álvaro.
- Design spec written: `docs/superpowers/specs/2026-09-12-cvforge-design.md`
  (governing principles, 14 approved decisions, data model, agent architecture,
  40 FRs + 10 NFRs, 9 milestones, CI/test strategy, `.claude` toolkit plan,
  plugin set). **That document is the authority on intent.**
- `git init` on `main`. No remote yet. No commits beyond documentation.

Not done yet — all of M0.

## Next action

Write the M0 + M1 implementation plan (the `superpowers:writing-plans` skill),
then execute M0.

M0 in order:
1. `pyproject.toml` (uv, Python 3.12+, ruff/mypy/pytest/coverage config),
   `.gitignore` (**`data/`, `*.db`, `cv_out/` first**), `.pre-commit-config.yaml`,
   `Makefile`.
2. `.claude/` toolkit: settings with the plugin set, 6 ported skills, 5 new
   skills, 4 agents, 4 hooks (see spec §10).
3. `.github/`: `ci.yml`, `security.yml`, `sanity.yml`, `dependabot.yml`, issue
   templates, PR template. No `board.yml` — no Kanban by decision D9.
4. `docs/requirements/srs.md` formalized from the spec's §6 catalogue; one GitHub
   issue per FR (labels `req:FR-xx`, milestones M0–M8).
5. `ADR-0001` (SQLite knowledge store with edge table) and `ADR-0002` (single
   uvicorn process serving API + SPA).
6. MkDocs site (Material + mkdocstrings, **no UML**), `mkdocs build --strict`.
7. Walking skeleton: FastAPI `/api/health`, SPA shell mounted at `/`, first tests,
   coverage gate green at 90%.
8. Create the public GitHub repo `SelfishCoconut/cvforge`, push, set branch
   protection with the required CI contexts.

## Milestones

| | Milestone | Delivers | Status |
|---|---|---|---|
| M0 | Foundations | Repo, CI/CD, coverage gate, security pipeline, SRS, ADRs, docs site, `.claude` toolkit, health skeleton | not started |
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
with a dedicated profile · React 19 + Tailwind v4 + headless primitives.
