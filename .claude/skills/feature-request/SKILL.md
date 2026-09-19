---
name: feature-request
description: Turn a plain-language feature request from Álvaro into a labeled GitHub issue (and optionally a feature branch). Use for "add a feature", "new feature request", "I want X", "turn this into an issue", "create a card for X".
---

# Feature request → board-ready issue

Front door for Álvaro's requests: convert an informal ask into a well-formed
GitHub issue, then optionally a branch, so request → issue → PR starts clean.

**No duplication:** requirement text is owned by the `requirements` skill, PR
creation by `commit-commands`. This skill orchestrates and calls those — it never
re-implements them.

## 1. Classify

- **Existing requirement** — already an `FR-xx`/`NFR-xx` in the SRS. Reuse the ID
  and the `req:FR-xx` label. Check `gh issue list --label req:FR-xx` first; most FRs
  already have an issue.
- **New product requirement** — a new behaviour of the system. **Stop and invoke
  the `requirements` skill first** to add it to the SRS (it assigns the next
  immutable ID), then come back. Never open a product-behaviour issue that is not
  in the SRS.
- **Infra / tooling** — CI, build, dev environment. Label `infra`, no FR. Title
  `<scope>: <title>`.
- **Bug** — label `bug`; reference the affected FR when known.

Ambiguous? Ask Álvaro.

## 2. Draft — do not create yet

Mirror `.github/ISSUE_TEMPLATE/feature.yml` so a `gh`-created issue matches a
template-created one:

- **Title**: `FR-xx: <imperative title>` or `<scope>: <title>`.
- **Body**: Requirement ID · Description (what must exist when done) · Acceptance
  criteria as checkboxes lifted from the SRS entry, runnable or checkable · MoSCoW
  priority.
- **Labels**: `feature` + `req:FR-xx` · `req:nonfunctional` · `infra` · `bug`.
- **Milestone**: the matching `M0`–`M8`.

Present the draft. **Nothing is created until Álvaro approves** — Claude never
opens scope-bearing items unilaterally.

## 3. Create on approval

The `req:FR-xx` label and the milestone are never left to a template or to
GitHub defaults — issue forms cannot set either, so this skill sets them
explicitly on creation:

```sh
gh issue create --title "FR-xx: <title>" --body-file <draft.md> \
  --label feature --label req:FR-xx --milestone "M1 Knowledge spine"
```

If the issue was created some other way (e.g. from the form) and is missing the
label or milestone, apply them explicitly and immediately:

```sh
gh issue edit <n> --add-label req:FR-xx --milestone "M1 Knowledge spine"
```

Then update the FR's `Traces to: issue #N` line via the `requirements` skill.

## 4. Optional — start the branch

```sh
git switch main && git pull
git switch -c feat/fr-xx-<slug>   # prefix = the Conventional-Commit type the work will use
```

The PR comes later, via `commit-commands`, and **must** contain `Closes #<issue>`.

## Definition of a good issue

Traces to a requirement (or is explicitly `infra`/`bug`); acceptance criteria are
runnable; correctly labelled and milestoned.
