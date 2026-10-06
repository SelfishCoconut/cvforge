# C1 — Chat, review, knowledge and settings UI: design

Date: 2026-10-05 · Status: draft, awaiting Álvaro's review
Scope: package C1 of `docs/superpowers/plans/2026-09-26-m1b-agent-layer.md`
(tasks C1.1–C1.7). Requirements: FR-13 (frontend half, issue #17), and the UI
side of FR-06/07/11/12/38/39, NFR-01, NFR-02. Decisions recorded in ADR-0015.

## Intent

Make the M1 backend operable by a person: talk to the assistant, review what it
proposes, browse what is stored and why, and configure the provider — without
the UI ever being able to weaken invariants 1–4. The UI is a client of the API;
it holds no authority over what is true.

## 1. Structure

- `frontend/src/api/`
  - Generated types: `openapi-typescript` over the committed
    `tests/golden/snapshots/openapi.json`, via `npm run gen:api`. CI fails when
    the generated file drifts from the snapshot.
  - A thin typed client (one function per endpoint used).
  - `readNdjson(response): AsyncIterable<Event>`.
- `frontend/src/features/{chat,review,knowledge,settings}/` — one folder per view.
- `frontend/src/ui/` — the few Radix-wrapped primitives: dialog, drawer, tabs,
  switch, tooltip.
- `frontend/src/app/` — shell, routes, query client.
- Routes: `/chat`, `/review` (queue), `/review/:id`, `/knowledge`,
  `/knowledge/:id`, `/settings`.
- Libraries: React Router and TanStack Query (server state), Radix UI
  (headless primitives). No shadcn/ui.

## 2. Visual direction (editorial)

- Serif for headings and evidence quotations; humanist sans for UI; mono only
  for ids and locators.
- One restrained accent, plus semantic colours for the four classifications
  (`new`, `known`, `duplicate`, `conflict`). Colour is never the only carrier of
  meaning: every badge also has its text label.
- Tokens are Tailwind v4 CSS variables; dark and light follow the OS.
- The direction is written down in `docs/architecture/frontend.md`.

## 3. Behaviour that carries risk

### Chat
- The composer posts to `POST /api/chat/messages/stream` (ADR-0014).
- `delta` events append to an `aria-live="polite"` region as they arrive.
- An `error` event shows an error state and ends the turn.
- A `proposal` event becomes an inline link to `/review/:id`. `ProposalView.id`
  is nullable: with no id there is nothing to review, so show the rejected items
  and no link.
- Assistant replies are not persisted (ADR-0014 D-F); a reload loses the
  transcript. The UI does not pretend otherwise.

### Review
- Each operation is a card: classification badge, the one-sentence explanation
  from ADR-0009's table, the evidence excerpt, and accept / edit / reject.
- **An `edited` operation is already approved** (plan audit F7): each decision
  replaces the previous one, so `accept` after `edit` would silently discard the
  edit. Its card offers *re-edit* and *reject*, never *accept*. A test asserts it.
- Commit is disabled while any operation is `pending`; when the server answers
  409 the UI shows its reason verbatim.
- Notices: `similarity_available=false` and non-empty `index_pending`.
- The queue (`/review`) lists proposals via the new `GET /api/proposals` (PR0).

### Knowledge
- Entities list filtered by kind and state.
- Detail shows the entity and its edges, and a "why?" drawer fed by
  `GET /api/provenance/{target_kind}/{target_id}`: source kind, locator and the
  literal excerpt.
- Read-only: the UI has no path that mutates knowledge (invariant 2/4).

### Settings
- `api_key_env` is a variable *name*; the copy says so.
- `allow_external` carries an explicit warning that content leaves the machine.
- `api_key_configured` is shown as a status. A key value is never requested,
  stored or rendered (ADR-0012).

### Untrusted content
Evidence excerpts, entity text and chat replies derive from attacker-controllable
documents. They render as text nodes only: no `dangerouslySetInnerHTML`, no
markdown-to-HTML of stored content, no link auto-activation. An ESLint rule bans
`dangerouslySetInnerHTML` in `src/`.

## 4. Testing and docs

- Vitest + Testing Library. The NDJSON reader is tested with a mocked `fetch`
  body stream: chunks split mid-line, a stream cut mid-object (surfaces an
  error), and `error` events (raise).
- The existing 90% branch-coverage gate stays. Keyboard paths are tested
  (card actions, drawer open/close with focus return, dialog escape).
- ADR-0015 records Radix, the editorial direction, and Router + Query.
- `docs/architecture/frontend.md` is authored with a Mermaid diagram of the
  module structure (no generated UML).

## 5. PR order (each mergeable alone)

| PR | Content | Closes |
|----|---------|--------|
| PR0 | Backend `GET /api/proposals` (additive OpenAPI diff; golden snapshot updated and reviewed) | issue to open (`infra`) |
| PR1 | Foundation: shell, tokens, generated types + drift CI, NDJSON reader, ADR-0015, `frontend.md` | C1.1, C1.2 |
| PR2 | Chat | #17 |
| PR3 | Review | C1.4 issue |
| PR4 | Knowledge | C1.5 issue |
| PR5 | Settings | C1.6 issue |
| PR6 | End-to-end demo (`TestModel` injected, no test-only switch in production code) and `-m system` test | C1.7 |

Per CLAUDE.md, each PR is preceded by its issue and carries "How to validate".

## Open points to settle in the plan, not here

- Exact shape of `GET /api/proposals` (filters, pagination, fields): minimal
  list of id, state, operation counts and created time unless the plan finds a
  need for more.
- Whether `/review` defaults to open proposals only.
