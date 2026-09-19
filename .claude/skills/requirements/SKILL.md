---
name: requirements
description: Create, update, or audit requirements in the SRS (docs/requirements/srs.md) and keep them in sync with labeled GitHub issues. Use for "add a requirement", "update FR-xx", "sync requirements to issues", or traceability checks.
---

# Requirements management (SRS ↔ GitHub issues)

`docs/requirements/srs.md` is the single source for requirements. Every functional
requirement maps 1:1 to a GitHub issue labelled `req:FR-xx`.

## Entry format

```markdown
### FR-12 — <imperative title>
- **Priority**: Must | Should | Could | Won't (MoSCoW)
- **Milestone**: M0–M8
- **Source**: design spec §n | elicitation YYYY-MM-DD | ADR-NNNN | change request
- **Description**: The system shall …  (one testable behaviour)
- **Acceptance criteria**:
  - [ ] concrete, executable check
- **Traces to**: issue #TBD, tests `tests/…`
```

`#TBD` is deliberate, and deliberately non-numeric. Replace it with the real
number in the same session that `gh issue create` returns one. The sync step
matches `issue #<digits>`, so a forgotten backfill makes the sync abort loudly
instead of freezing a placeholder into a published issue body — which is exactly
how the string `issue #N` once reached all 40 of them.

NFRs use `NFR-xx` with a measurable target ("p95 proposal round-trip < 30 s on
qwen3.6:27b", never "fast").

## Rules

- IDs are immutable and never reused. A new requirement takes the next free number.
- A requirement must be testable. If the acceptance criteria cannot be phrased as
  something runnable, split or rephrase it.
- **Every criterion states the negative case too.** For "the system does X", add
  "and when the precondition is absent it refuses rather than guessing". That half
  is what protects the invariants in CLAUDE.md.
- Requirements changes are Álvaro's decisions: draft, confirm, then commit. A scope
  change also gets an ADR.
- **Sync (ADR-0004 — the SRS is the source of requirement text):** each FR gets an
  issue titled `FR-xx: <title>` labelled `feature` + `req:FR-xx` with the matching
  milestone. The issue body is a **generated projection** of its SRS block — the
  block minus its `### ID — title` heading, with the `issue #<n>, ` fragment
  stripped from the `Traces to` line, followed by the `SRS entry:` / `Design
  spec:` trailer — never a separately authored or hand-patched text. **An SRS
  edit is not finished until the tracker is re-synced**: regenerate the body from
  the updated block and push it, e.g. `gh issue edit <n> --body-file
  <generated.md>`. Never hand-patch an issue body to fix or extend it — a
  correction typed there is silently lost on the next sync; discussion belongs in
  a comment, not the body. `scripts/sync_issues.py` (tracked as issue #50) will
  automate this with a `--check` mode for CI drift detection; it does not exist
  yet, so until it does, treat every re-sync as a manual step and do not skip it.
- Traceability audit (on request, and before closing a milestone): every FR has an
  issue; every closed FR issue has merged PRs referencing it and tests that
  exercise the behaviour. Report orphans.
