# CVForge

A local-first personal professional knowledge system: it records everything you
know and have done professionally — with the evidence behind each fact — and uses
that knowledge to analyze job openings, generate tailored CVs, find gaps in your
skills, plan how to close them, and prepare you for interviews.

Not an AI CV generator. The CV is one output of a knowledge base that is the
source of truth.

## Status

M0 (foundations) is done. M1 (the knowledge spine) is in progress: the knowledge
store and review pipeline (M1a) are in; the agent layer and the UI are next. See
`docs/roadmap.md` for current state and the next action.

## Run it

```sh
make build-ui    # build the SPA — without this, / returns 404 and only /api works
make run         # http://127.0.0.1:8000 — SPA and API from one process
```

`make demo-health` proves the skeleton works offline, with no server and no build.
`make demo-review-pipeline` walks the whole intake → proposal → review → commit
loop the same way. The knowledge base is one file, `data/cvforge.db`; the export
procedure is in `docs/architecture/knowledge-model.md`.

## Develop

```sh
uv sync                      # Python 3.13 environment
uv run pre-commit install    # commit-time gates
make lint typecheck complexity
make test                    # unit + integration + golden
make migration MSG="what changed"   # new Alembic revision after editing kb/schema.py
make docs-serve              # documentation site at :8000
```

## The five invariants

1. The database is the source of truth, not the LLM.
2. `src/cvforge/kb/apply.py` is the only module that writes entity, edge or
   assertion rows. Agents have no write tools.
3. No entity and no edge exists without at least one assertion bound to an
   evidence span in a source.
4. Nothing reaches the database without review: agents propose, you accept, edit
   or reject each operation, and the commit is atomic.
5. Automatic-mode CV generation never emits a claim without a stored assertion.

## Privacy

Your knowledge base, documents, CVs and browser profile live in `data/`, which is
gitignored and never leaves the machine. The default model backend is a local
Ollama endpoint; Anthropic, OpenAI and web search are opt-in. Fetched web pages
and uploaded documents are treated as untrusted data — analyzed, never obeyed.

## Licence

AGPL-3.0-or-later.
