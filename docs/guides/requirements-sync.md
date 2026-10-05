# Keeping requirement issues in sync

`docs/requirements/srs.md` is the authority on requirements; every requirement
issue carries a **copy** of its SRS block. `scripts/sync_issues.py` regenerates
those copies so an SRS edit cannot leave the public tracker asserting old text.

```
uv run python scripts/sync_issues.py --check   # exit 1 on drift, naming the IDs
uv run python scripts/sync_issues.py           # rewrite only the drifted issues
```

- All bodies are generated and validated before any issue is written, so a
  malformed block (no `Traces to` line, two of them, a trace naming only an
  issue, a residual `issue #n`, a duplicated ID or issue) aborts the whole run
  with exit code 2.
- A body is the requirement block without its heading, with the leading
  `issue #<n>, ` removed from `Traces to`, followed by the `SRS entry:` and
  `Design spec:` trailer. It has no trailing newline, so a re-run on a synced
  tracker performs zero writes.
- Requirements tracing only to issue #1 (the milestone epic) have no issue of
  their own and are skipped.
- When `Traces to` lists several issues (`issues #12 and #48`), only the first
  is the requirement's copy. The others are decision or tracking threads with
  content of their own and are never rewritten.

Run it after any SRS edit, in the same PR; `--check` is cheap enough to gate in CI.
