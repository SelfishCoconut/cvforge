# 0002. One uvicorn process serves both the JSON API and the built SPA

Date: 2026-09-12
Status: accepted

## Context

CVForge has a React front end and a Python back end. A local single-user tool
should be startable with one command, with no reverse proxy, no CORS
configuration, and no second port to remember.

## Decision

We will serve everything from one uvicorn process. FastAPI mounts the JSON API
under `/api`, and the built SPA is mounted at `/` from `frontend/dist` — but only
when `frontend/dist/index.html` exists. The process binds `127.0.0.1` only, and
`Settings` rejects any non-loopback host.

During front-end development a second process (the Vite dev server) proxies
`/api` to the backend, so relative paths work the same in both modes.

## Alternatives considered

- **Two long-running services behind a proxy.** Standard for deployment, and
  entirely unnecessary overhead for a tool that runs on one laptop.
- **Serving the SPA from a separate static server.** Adds CORS configuration and
  a second thing to start, for no benefit.

## Consequences

- `make run` without `make build-ui` gives a working API and a 404 at `/`. This
  is an explicit, tested behaviour rather than a crash, and it is the first thing
  to check when the UI "disappears".
- The static mount is registered after the API routes, so `/api/...` always wins
  over the SPA catch-all. An integration test pins this; reversing the order is a
  silent, total API outage.
- There is no authentication anywhere. That is sound only because the process is
  unreachable from off the machine, which is why the loopback check is code and
  not a comment.
