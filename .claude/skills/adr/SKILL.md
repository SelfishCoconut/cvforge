---
name: adr
description: Create or update an Architecture Decision Record in docs/adr/ (MADR format). Use whenever a significant design, architecture or scope decision is made, or when the user says "record this decision".
---

# Architecture Decision Records

ADRs are the durable record of *why*. They are what survives a cleared
conversation, so a decision without an ADR effectively does not exist.

## Format (MADR, one file per decision)

File: `docs/adr/NNNN-short-kebab-title.md` — `NNNN` is the next sequential number;
check existing files.

```markdown
# NNNN. <Title — the decision, stated as a fact>

Date: YYYY-MM-DD
Status: accepted | proposed | superseded by [NNNN](link) | deprecated

## Context
What forces are at play; why a decision is needed now.

## Decision
What Álvaro decided. Active voice: "We will…"

## Alternatives considered
Each rejected option and the concrete reason it lost.

## Consequences
What becomes easier, what becomes harder, what debt is accepted.
```

## Rules

- **Adding an ADR is a three-file change, every time**: the new
  `docs/adr/NNNN-*.md` itself, a new row in the index table in
  `docs/adr/README.md` (number, title, status, date), **and** a new entry under
  `Decisions:` in `mkdocs.yml`'s `nav:`. Miss the nav entry and the page is
  unreachable from the site even though the file itself is well-formed —
  `mkdocs build --strict` (the `docs` skill's required CI gate) fails on the
  resulting orphan page, so treat all three edits as one change and land them in
  the same commit.
- The decision-maker is Álvaro. If he has not explicitly decided, write the ADR
  with status `proposed` and ask — never mark `accepted` on his behalf.
- Also register it in the codebase-memory graph with `manage_adr`, so structural
  queries surface it.
- Supersede, never rewrite history: a changed decision gets a new ADR linking
  back. This is the index's own rule — never edit an accepted ADR's decision
  after the fact.
- "Alternatives considered" is not optional. An ADR that lists no rejected option
  is a note, not a decision record.
