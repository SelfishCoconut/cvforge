# 0019. Job pages are fetched static-first, with an optional browser fallback and a local-address bar

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-17 fetches a job posting by URL (spec D12: `httpx` + `trafilatura`, Playwright for
JavaScript-rendered boards). The URL is typed by Álvaro but the page, and every
redirect it issues, is attacker-controlled data (NFR-07). The API runs on his machine,
so a fetcher that follows any URL is also a way to make that machine request
`http://169.254.169.254/` or `http://localhost:…` on a page's behalf.

## Decision

**D-K — static first.** `web/fetch.py:fetch_page` does an `httpx` GET and reduces the
HTML with `trafilatura`. If the text is under 200 characters the page is assumed to be
rendered by JavaScript and a `BrowserFetcher` renders it instead. With no fetcher
configured that is a `FetchError`, never an empty result.

**D-L — Playwright is an optional extra** (`cvforge[browser]`), imported only when a
page is rendered, with a throwaway context (no stored login, not M8's persistent
profile). Static fetching must work on a machine without a browser.

**D-M — only public http(s) targets.** Other schemes are refused. `localhost`,
`*.localhost` and IP literals that are not globally routable (loopback, private,
link-local) are refused, on the first URL and on every redirect hop. Redirects are
followed by hand (at most 5) so each hop is checked. Responses are capped at 5 MiB.
`allow_local=True` exists for tests and the offline demo only.

**D-N — fetching never acts.** A fetch returns text and nothing else: no entity, edge
or proposal. Analysis (FR-18) and persistence (FR-20) are separate steps.

## Consequences

- A hostname that *resolves* to a private address (DNS rebinding, or an internal
  hostname) is not caught: the check is on literals, to stay offline and deterministic.
  Resolving and pinning the address is the follow-up if this tool is ever exposed
  beyond one user's machine.
- The browser fallback checks only the URL it is given; subresources and in-page
  redirects inside Chromium are not filtered.
- Some boards block non-browser clients; they surface as an HTTP error, and the user
  can paste the posting text instead (a later task).
