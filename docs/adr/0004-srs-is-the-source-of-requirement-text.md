# 0004. The SRS is the source of requirement text; issue bodies are generated from it

Date: 2026-09-19
Status: accepted

## Context

`docs/requirements/srs.md` holds 40 functional and 10 non-functional
requirements, each a block of six fields. Every requirement that has one also has
a GitHub issue (#5–#47) whose body carries a **copy** of that block, so the
acceptance criteria are readable where the work is tracked.

Those copies were written once, at issue-creation time, and nothing kept them
current. The failure was not theoretical. A review of the requirements catalogue
corrected two requirements — FR-34 asserted a `gap → learning → confirmed` state
machine the design spec does not define, and FR-29 required a `Must`-priority
match against a field whose vocabulary has no `Must` in it. Both corrections
landed in the SRS. Neither reached the tracker. The public issues went on
asserting the withdrawn text, and the scoped fix would have "passed" while
leaving exactly the defects it existed to remove.

The same edit had already been made twice from different directions: the SRS
carried an `issue #N` placeholder frozen into all 40 bodies, and three
hand-created issues used a reduced body with three of the six fields missing.
Three divergences, one cause.

## Decision

The SRS is the single source of requirement text. An issue body is a **generated
projection** of its SRS block, never separately authored or separately patched.

- The body is the SRS block minus its `### ID — title` heading, with the
  `issue #<n>, ` fragment stripped from the `Traces to` line (inside the tracker
  that direction is served by the URL), followed by the `SRS entry:` /
  `Design spec:` trailer, and no trailing newline.
- When the SRS and an issue disagree, the SRS wins and the issue is regenerated.
- An SRS edit is not finished until the tracker is re-synced.
- Generate and validate every body before writing any: a malformed block aborts
  the whole run rather than publishing a partial rewrite.

`scripts/sync_issues.py` is the durable form of this, tracked as issue #50, with
a `--check` mode so CI can fail on drift.

## Alternatives considered

- **Keep the issue body authored by hand and treat drift as a review
  responsibility.** This is what we had. It failed on its first real test, and it
  fails silently: nothing surfaces the divergence, and the wrong copy is the
  public one.
- **Put only a link to the SRS in the issue body.** Guarantees consistency and is
  much less machinery. Rejected because the acceptance criteria are the reason to
  open the issue at all — a tracker item that says only "see the SRS" cannot be
  triaged, estimated or checked off where the work happens.
- **Make the tracker the source and generate the SRS from it.** Rejected: the SRS
  is reviewable as a single diff, survives the repo being cloned without network
  access, and is the artifact CLAUDE.md names as the authority on requirements.

## Consequences

- Editing a requirement is a two-step operation, and the second step is easy to
  forget. `--check` in CI is what makes the rule real rather than aspirational.
- Issue bodies must not be edited by hand. A correction made in the tracker is
  lost on the next sync — discussion belongs in comments, which sync does not
  touch.
- The generator's output format is now load-bearing. It was validated by
  regenerating four untouched bodies and confirming they came back byte-identical
  to what was already published; any future change to the format must clear the
  same bar.
- Requirements tracing only to the milestone epic (#1) have no issue of their own
  and are outside the sync. That is a deliberate gap, not an oversight.
