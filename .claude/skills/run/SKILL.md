---
name: run
description: Launch CVForge locally so the whole tool (React SPA + FastAPI /api) is operable in the browser. Use for "start the project", "run the app", "serve it locally", or checking the frontend/backend end to end.
---

# Run CVForge locally

Everything runs from **one uvicorn process** (ADR-0002): FastAPI serves the JSON
API under `/api` and the built React SPA at `/`. It binds `127.0.0.1` only
(NFR-02) — `Settings` refuses any other host. There is no authentication.

## Fastest full-stack run

```bash
make build-ui   # builds frontend/dist — REQUIRED, or / is API-only
make run        # uvicorn on http://127.0.0.1:8000
```

- **The SPA is mounted only when `frontend/dist/index.html` exists**
  (`_mount_spa` in `src/cvforge/app.py` returns False otherwise). Without a build
  you get a working `/api` and a 404 at `/`. This is tested behaviour, not a bug —
  and it is the first thing to check when "the UI disappeared".
- `make run` is foreground. To keep it alive while working:
  `make run > /tmp/cvforge.log 2>&1 &`
- For SPA iteration with hot reload, two processes: `make run` plus `make dev-ui`
  (Vite proxies `/api` to 127.0.0.1:8000, so relative paths behave identically).

## Smoke tests

```bash
curl -s http://127.0.0.1:8000/api/health                             # {"status":"ok","version":"..."}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/      # 200 once built
```

Interactive API docs: http://127.0.0.1:8000/docs.

## Offline proof, no server needed

`make demo-health` exercises the app in-process and prints the health payload.
`make test-demos` runs every offline demo — CI runs the same target, so a broken
demo fails the build.

## LLM backend (from M1 on)

Default is the local Ollama endpoint with `qwen3.6:27b`; `nomic-embed-text`
provides embeddings. Environment variables **seed** the persisted settings on
first run only — after that, change provider, model or base URL in the `/settings`
view at runtime, with no restart. Anthropic and OpenAI are opt-in alternatives.

## State and cleanup

The knowledge base is a single SQLite file under `data/` (gitignored). Delete it to
reset. `make clean` removes build and cache artifacts but never touches `data/`.
