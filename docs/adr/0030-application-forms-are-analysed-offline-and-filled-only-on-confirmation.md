# 0030. Application forms are analysed offline and filled only on confirmation

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

M8 helps with application forms (spec D13). A form page is untrusted data (NFR-07), filling
touches the user's real applications, and an automatic submit could send something unreviewed. The
design has to make "analyse, suggest, confirm, fill, never submit" structural.

## Decision

**D-AY — analysis is a pure function of HTML.** `forms/analyze.py` parses markup with the standard
library (no new dependency, no script execution) and returns `FormField`s: label (label-for, wrapping
label, `aria-label`, placeholder, `name`, else a `Field N` placeholder, never dropped), inferred type,
required flag, options for selects and radio groups, and a Playwright selector kept server-side.
Hidden inputs, buttons and disabled controls are not fields; password fields are listed as
`sensitive` and are never suggested or filled. A page without a form yields an empty list.

**D-AZ — getting the HTML reuses the job-page fetcher.** `web.fetch.fetch_html` has the same
safeguards (public http(s) only, resolved-address check, size and time caps) and falls back to the
optional Playwright renderer only when the static HTML, scripts removed, holds no `<form`. Tests
serve local fixtures; the integration job installs headless Chromium for the JavaScript-built case.

**D-BA — (FR-36/37, later PRs) suggestions come only from stored data; fill writes only confirmed
fields and never submits.** Defaults are derived from the knowledge base and the selected CV or
left blank and flagged; a session stores them in `form_fill_session.fields_json`. The fill routine
writes a field only after the user confirmed its value, runs in a headed persistent profile under
`data/` (never the user's own browser profile), and no code under `forms/` may click, submit or
press Enter on a submit control (an AST test pins this).

**D-BB — the API.** `POST /api/forms/analyze` previews fields; `POST /api/forms/fills` stores
suggestions drawn from a chosen CV, `PUT`/`DELETE .../fields/{key}` confirm or withdraw a value,
and `POST .../fill` opens the visible browser and returns when the window is closed. The path
says `fills`, not `sessions`, because NFR-02's route-inventory test forbids session endpoints.
The fill's browser screens requests and WebSockets like the job fetcher, and fetches each request
without following redirects so a redirect hop is checked before it is requested; DNS rebinding inside
Chromium is a known, unmitigated limit shared with it.

## Consequences

- Selectors are positional when a control has no `id`, so a page that changes between analysis and
  fill can mis-target; the fill step re-checks the label before writing.
- Multi-step wizards and iframes are not analysed; each page is analysed separately.
