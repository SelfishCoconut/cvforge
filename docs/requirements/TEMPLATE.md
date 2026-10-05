# Requirement entry template

Copy this block into `srs.md` under the right section and fill every field. Do not
copy an existing entry: its numbering, criteria count and wording are specific to it.
Requirement changes are Álvaro's decisions: draft, confirm, then commit.

```markdown
### FR-NN — Short imperative title
- **Priority**: Must | Should | Could | Won't
- **Milestone**: M0–M8
- **Source**: design spec §x.y
- **Description**: The system shall <one testable behaviour>.
- **Acceptance criteria**:
  - [ ] <positive check, phrased so a test can assert it>
  - [ ] <its negative case: refuses or fails safely when the precondition is absent>
- **Traces to**: issue #<n>, tests `tests/unit/test_<name>.py`
```

Rules of thumb:

- The ID is the next free number and is never reused.
- Use as many criteria as the behaviour needs, not a fixed four. Never restate one
  criterion to reach a count.
- Every criterion must be assertable. Replace "clear error", "concrete" or
  "demonstrably" with the exact observable: an exception type, an HTTP status, a
  field that must be present.
- `Traces to` starts with `issue #<n>, ` (the issue that carries the requirement;
  `scripts/sync_issues.py` strips it from the issue body) followed by the tests or
  config files that enforce it. Non-functional requirements name a config or
  workflow file instead of a test.
- Tick a box only when a committed test or check proves it, then run
  `uv run python scripts/sync_issues.py` so the issue matches.
