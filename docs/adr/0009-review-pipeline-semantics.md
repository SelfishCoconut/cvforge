# 0009. Review-pipeline semantics: what is written when, and what the four classifications mean

Date: 2026-09-21
Status: accepted (decided by Claude under Álvaro's standing delegation of 2026-09-20; reported to him afterwards)

## Context

ADR-0003 fixed the shape: agents propose, Álvaro reviews each operation, and
`kb/apply.py` commits. Building it (M1a) forced four questions that neither the
spec nor ADR-0003 answers. Each one is a behaviour Álvaro will see every day in
the review UI.

1. **`known` versus `duplicate`** (issue #48). Spec §4.5 lists both values and
   never separates them. FR-08 and FR-16 accepted either, so a classifier that
   never emitted `known` would have passed.
2. **What is written before review?** Invariant 4 says "nothing reaches the
   database without review", but an operation must cite evidence, and evidence
   must exist before a proposal can refer to it.
3. **Who classifies?** The model, or the database?
4. **What does *accepting* each classification do?**

The schema is expected to be reshaped several times as the tool gets used, so
each answer also has to stay cheap to revise.

## Decision

**Intake writes provenance. Commit writes knowledge.** `source` and `evidence`
rows are written at capture time: the chat message or document span exists
whether or not any fact drawn from it is accepted. `entity`, `edge` and
`assertion` rows are written only by `commit_proposal`. Every write of either
kind is still in `kb/apply.py`. Its public surface is five functions, and a test
fixes that surface, so adding a sixth writer is a visible, reviewed change.

**The database classifies, not the model.** `kb/classify.py` compares each
candidate operation with stored rows, deterministically. The model's opinion of
novelty is never trusted, because the database is the source of truth
(invariant 1).

**The four values:**

| Value | Means | Accepting it |
|---|---|---|
| `new` | Nothing stored covers it | Creates or changes rows |
| `known` | The same thing is already recorded: same kind and normalized name, same field value, or same edge triple | Adds this evidence as another assertion on the existing record. No new entity or edge |
| `duplicate` | A differently named record is probably the same thing, found by similarity search (FR-05, M1b) | Links to that record, as `known` does. Folding two *stored* entities together is `merge_duplicate`, applied from M1b |
| `conflict` | The same field or edge is recorded with a different value | Replaces the stored value. The old assertion stays as history |

`known` is decided by name only for kinds whose name is their identity: `skill`,
`organization`, `project` and `credential`. Two roles called "Software Engineer"
are routinely different facts, so a name match proves nothing for `role`,
`education`, `achievement` or `responsibility`.

Operations are **atomic per proposal**. If any accepted operation fails, for
example an edge referring to a creation the reviewer rejected, nothing from the
proposal is kept, and it stays open for re-review.

Two schema refinements follow from the same reasoning:

- `operation` names its classification target with `(target_kind, target_id)`
  instead of the spec's `target_entity_id` + `conflict_with_id`, because FR-08
  requires naming an entity *or* an edge.
- `credential` has no `issuer` text column. Spec §4.1's prose makes the issuer an
  `at_organization` edge.

## Alternatives considered

- **`known` means an exact match, `duplicate` means any match.** Rejected. That
  is the ambiguity #48 describes, and the words carry no information the target
  id does not.
- **Write evidence only at commit, carried inline in the payload.** Rejected. A
  proposal could then cite text that no row records. FR-12 requires the
  foreign key to be enforced, not conventional. It would also duplicate
  excerpts across every operation drawn from one message.
- **Let the model classify, with the database as a check.** Rejected. A model
  that says "new" about a stored fact would be overruled every time, so the
  model's answer adds latency and a failure mode and nothing else.
- **Partial commits: keep the operations that succeeded.** Rejected. It leaves
  the knowledge base in a state no reviewer approved as a whole (FR-10).
- **Classify `known` by name for every kind.** Rejected for the role and
  achievement reason above. Better signals (dates, the employer edge) arrive with
  similarity search.

## Consequences

- The review UI (M1c) can explain every operation in one sentence, taken from
  the table above.
- `duplicate` exists in the schema and the classifier today, but nothing emits
  it until similarity search lands. That is tested through an injected finder,
  not faked.
- `merge_duplicate` validates but refuses to apply until M1b. The commit fails
  loudly rather than doing half a merge.
- Changing a classification rule is a change to one pure module, plus its tests
  and this ADR. No migration is needed, which keeps the most-likely-to-change
  logic out of the schema.
- FR-08 and FR-16 are rewritten to assert exactly one value per case. Issue #48
  closes with this ADR.
