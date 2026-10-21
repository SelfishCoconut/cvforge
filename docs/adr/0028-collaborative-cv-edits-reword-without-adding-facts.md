# 0028. Collaborative CV edits may reword but never add a fact

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-31 lets the user edit a generated CV in conversation: reword a bullet, shorten, shift
emphasis. A reworded bullet is no longer copied from a stored fact (ADR-0024), yet it must
keep its entity and assertion link and must not become a way to invent a skill, a number or a
leadership role.

## Decision

**D-AS — a new claim basis, `reword`.** A reworded claim keeps the original `entity_id` and
`assertion_id` (the assertion must still be a `name` or `summary` one), carries the new text, and
is checked by the same `binding.claim_problem` as every other claim, in the store and in the
validator. For `reword` the check replaces "text equals the stored fact" with a grounding check
(`cv/grounding.py`): the new text may not grow more than three words past the stored line; every number (NFKC-
normalised, in the stored order, `%` kept), every non-initial capitalised term, every token naming
another stored entity, every strong-claim or seniority stem (lead, manag, found, senior, expert...,
including Spanish forms) and every negation must already appear in the facts about the entity or
the names of its *confirmed* neighbours through `used_in`/`part_of`/`at_organization`/`produced`/
`involved`. The cited assertion must still be the latest one for its field with the entity's current
value. A `reword` claim is refused in an automatic CV by the store and flagged by the validator
(`reword_in_automatic`). This is a heuristic backstop; plain wording is free, and a human reviews a
draft before it is final. Known residual: an unstored proper noun leading the line, or a lowercase
claim made of ordinary words, can still pass (found by the FR-31 audit; mitigated by the growth cap).

**D-AT — edits are operations the code checks one by one.** The edit agent (tool-free, the CV
fenced as data) proposes `reword` / `drop` / `emphasize`; `cv/edit.py` applies each against the
stored facts and refuses, with a reason, any it cannot support: rewording a header or period,
a reword that fails grounding, emphasising a name nothing confirmed is stored about (redirected
to chat or a discovery question so it can be reviewed and recorded), or a skill that is only a
recorded gap. The rest still apply.

**D-AU — every edit is a new `collaborative` version** (`parent_cv_id`, ADR-0026); history is
never mutated. The new version is validated and its issues returned: dropping a required skill the
candidate is `satisfied` on yields `incomplete_coverage`, and a version with issues cannot be
finalised, rendered or sent.

## Consequences

- Collaborative mode is the only place a claim's words are not a stored string; the grounding
  heuristic can miss a lowercase ordinary-word claim ("built a payments system" from "built a
  parser"). The draft/validate/review path is the second line, not the heuristic alone.
- `reword` claims render exactly like others, and survive re-validation as long as the entity
  and its related names still ground them.
