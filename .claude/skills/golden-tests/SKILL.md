---
name: golden-tests
description: Record, review and update golden snapshots in tests/golden/. Use when a golden test fails, when adding a snapshot for new behaviour, or when deciding whether a snapshot change is a regression or an intended change.
---

# Golden snapshots

The second regression layer. Coverage proves code ran; golden snapshots prove it
still produces the same thing. In an LLM system this is the layer that catches the
failure that matters: a prompt or pipeline tweak quietly changing what gets
extracted, with every test green and coverage full.

## How it works

- `tests/golden/` holds the tests; `tests/golden/snapshots/*.json` the committed
  expectations.
- The `golden(name, value)` fixture renders `value` as key-sorted, indented JSON
  and compares it byte-for-byte.
- `make update-golden` (`pytest -m golden --no-cov --update-golden`) rewrites
  snapshots and reports the tests as **skipped**, so an update run can never be
  mistaken for a pass.
- CI never passes `--update-golden`. There, the snapshot is the expectation.

## When a golden test fails

**A failure is a regression until proven otherwise.** Work in this order:

1. **Read the diff.** `git diff tests/golden/snapshots/` after regenerating
   locally. Do not regenerate-and-commit before reading.
2. **Ask what changed the output.** A prompt edit, a schema change, a model
   default, a normalization tweak? If you cannot name the cause, you have found a
   bug, not a snapshot that needs updating.
3. **If the change is wrong**, fix the code. The snapshot was right.
4. **If the change is intended**, run `make update-golden`, commit the snapshot in
   the *same* PR as the cause, and fill the PR template's "Golden snapshot changes"
   section with what changed and why it is correct.

## Adding a snapshot

Snapshot the *meaning*, not incidental detail. Strip values that churn without
behaviour changing — versions, timestamps, generated ids — before comparing, the
way `test_openapi_snapshot.py` pops `info.version`. A snapshot that churns on every
run teaches everyone to regenerate without reading, which destroys the gate.

Good subjects: the proposal an agent produces for a fixed input; a job analysis
for a recorded page; the LaTeX body for a fixed knowledge base; the OpenAPI schema.

## Red flags

| Symptom | Meaning |
|---|---|
| `make update-golden` in a PR with no explanation | the gate was bypassed; `regression-guard` will flag it |
| A snapshot changed by a PR that claims to be a refactor | a refactor that changes output is not a refactor |
| A snapshot containing a timestamp or a UUID | it will churn; strip it |
| Golden tests hitting a live model | forbidden; use `FunctionModel` |
