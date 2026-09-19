---
name: release
description: Close out a milestone — verify the gates, run the sanity audit, bump the version, tag, and update the roadmap. Use when the user says "close M<n>", "cut a release", or "we're done with this milestone".
---

# Milestone close-out

A milestone is done when its requirements are *demonstrably* done, not when its
issues are closed.

## 1. Verify, do not assume

```bash
make lint && make typecheck && make complexity
make test            # unit + integration + golden
make test-demos
make docs
gh run list --branch main --limit 5
```

Every one must pass, with output seen. Then the traceability audit:

```bash
gh issue list --milestone "M<n> <name>" --state open        # expect empty
gh issue list --milestone "M<n> <name>" --state closed --json number,title
```

For each closed FR, confirm the SRS acceptance criteria are actually ticked and
that tests exercise the behaviour. An FR closed without a test that would fail if
the behaviour broke is not done — reopen it.

## 2. Audit the codebase

Run the `codebase-sanity` agent. Its report lands in `docs/sanity/YYYY-MM-DD.md`
with a HEALTHY / WATCH / DEGRADING verdict per category, compared against the
previous report. Must-fix findings become `tech-debt` issues before the tag, not
after.

## 3. Bump, tag, record

- Bump `version` in `pyproject.toml` (minor per milestone: M1 → `0.2.0`).
- Update `docs/roadmap.md`: mark the milestone done, set the next action, update
  the status table. This is the file the next session reads first — it is the
  deliverable, not an afterthought.
- Write the progress report with the `progress-report` skill.

```bash
git tag -a v0.<n>.0 -m "M<n>: <milestone name>"
git push --tags
gh release create v0.<n>.0 --title "M<n> — <name>" --notes-file docs/reports/<date>.md
gh api repos/:owner/:repo/milestones --jq '.[] | select(.title|startswith("M<n>")) | .number'
# gh has no native "milestone" subcommand; close it by number via the REST API:
gh api -X PATCH repos/:owner/:repo/milestones/<number> -f state=closed
```

## 4. Hard rules

- Never tag with a red CI run on `main`.
- Never close a milestone with open issues in it — move them out explicitly, with
  a reason, so the scope change is visible.
- Coverage at or above 90% is a release gate, not a guideline.
