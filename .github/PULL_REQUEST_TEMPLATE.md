<!-- .github/PULL_REQUEST_TEMPLATE.md -->
## What & why

Closes #<issue>. <!-- Every PR traces to an issue -->

<one paragraph: what this changes and why>

## How to validate (mandatory)

```sh
# exact commands to run
```

**Expected output / behavior:**

<what Álvaro should see>

**Acceptance criteria** (from the requirement, tick after personally verifying):

- [ ] …

## Self-review checklist

- [ ] I ran the validation steps above myself and the behavior is correct
- [ ] Tests added/updated at the right level (unit / integration / golden / system)
- [ ] Coverage still ≥90% line and branch; no test skipped without an issue reference
- [ ] Golden snapshots unchanged, or changed deliberately and justified below
- [ ] Docstrings on new/changed public symbols; affected docs and diagrams updated
- [ ] No personal data introduced — fixtures are synthetic, `data/` untouched
- [ ] Knowledge-base writes (if any) go only through `kb/apply.py`, and every new
      entity or edge is backed by an assertion
- [ ] Significant decisions recorded as an ADR

## Golden snapshot changes

<if any snapshot under tests/golden/snapshots/ changed, say which and why it is
correct rather than a regression; otherwise write "none">
