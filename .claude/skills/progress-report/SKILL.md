---
name: progress-report
description: Generate an on-demand progress summary (commits, closed issues, milestone status, open questions) since a given date. Use when the user asks for a status write-up or progress report.
---

# Progress report

On-demand summary of movement since a date Álvaro gives (default: the last report
in `docs/reports/`, else the last 14 days).

## Gather

```sh
git log --oneline --since=<date>
git diff --stat <date-ref>..HEAD
gh issue list --state closed --search "closed:><date>"
gh issue list --state open --label feature
gh api repos/:owner/:repo/milestones --jq '.[] | "\(.title): \(.closed_issues)/\(.open_issues + .closed_issues)"'
gh pr list --state merged --search "merged:><date>"
```

Also read `docs/roadmap.md` for the declared current state, and the newest file in
`docs/sanity/` for the quality trend.

## Output

Terse markdown saved to `docs/reports/YYYY-MM-DD.md`:

1. **Done** — merged and validated, one line each with the issue reference.
2. **In flight** — open work and what blocks it.
3. **Metrics** — throughput, coverage trend, complexity trend.
4. **Decisions taken** — ADRs added in the period.
5. **Open questions** — what needs Álvaro's decision.

Factual, no filler. Then update `docs/roadmap.md` so the next session starts from
the truth.
