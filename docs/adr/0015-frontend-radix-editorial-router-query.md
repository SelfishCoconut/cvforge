# 0015. The frontend: Radix primitives, an editorial look, React Router and TanStack Query, generated API types

Date: 2026-10-05
Status: proposed — decided by Claude under Álvaro's delegation; awaits his
confirmation. Confirm to mark it accepted.

## Context

C1 builds the chat, review, knowledge and settings UI (FR-13, frontend half).
CLAUDE.md fixes the stack (React 19, TypeScript, Vite, Tailwind v4, headless
primitives, no shadcn/ui) but leaves the primitive library, routing, server-state
handling, type source and visual direction open. The SPA also reads
attacker-influenced text (job pages, uploaded documents), and the backend is one
process serving both the API and the SPA (ADR-0002).

## Decision

- **Radix UI** for the headless primitives, one package per primitive. Because Radix
  ships no drawer, the "why?" provenance drawer is a Radix `Dialog` styled as a side
  sheet.
- **Editorial visual direction**: pale, faintly warm paper surface, graphite ink, a
  single fountain-pen blue accent, serif headings, system font stacks only (no remote
  fonts). Classification badges are label-on-tint, never colour alone. Tokens live in
  `frontend/src/index.css`; see `docs/architecture/frontend.md`.
- **React Router v8 (`BrowserRouter`)** for navigation and **TanStack Query** for
  server state. The backend serves `index.html` for unknown non-API paths (history
  fallback) so a deep link such as `/review/3` survives a reload.
- **API types are generated** by `openapi-typescript` from the committed OpenAPI
  snapshot (`tests/golden/snapshots/openapi.json`). CI regenerates and runs
  `git diff --exit-code` on `src/api/schema.d.ts`, so a backend change that is not
  reflected in the types fails the build.
- **`dangerouslySetInnerHTML` is banned** by an ESLint `no-restricted-syntax` rule.
  Text from jobs, documents and the model is rendered as text, never as markup.
- **An `edited` operation is already approved** (plan audit F7). Each decision replaces
  the previous one, so `accept` after `edit` would silently discard the edit. Review
  cards for an `edited` operation offer re-edit and reject, never accept; a test
  asserts it.

## Alternatives considered

- **React Aria Components.** Rejected: larger surface and an opinionated component
  layer; Radix's per-primitive packages let us take only what we use.
- **shadcn/ui.** Rejected by CLAUDE.md: it would read as templated.
- **Hand-written types or a runtime schema library.** Rejected: they drift silently;
  generated types plus a drift gate cannot.
- **A tooltip primitive.** Dropped as YAGNI: nothing in C1 needs one.
- **Redux or a hand-rolled fetch cache.** Rejected: TanStack Query covers the server
  state this UI has, and there is no meaningful client-only state to store.

## Consequences

- React Router 8 requires Node >= 22.22; CI uses Node 22 and local development must too.
- The drawer is a styled Dialog, so it gets Radix's focus trapping and Escape handling
  but has to supply its own side-sheet layout and motion.
- Changing the API now means regenerating `schema.d.ts` in the same PR.
- The lint ban means any future need for rich text needs a sanitising renderer
  decided in its own ADR, not a one-off escape hatch.
