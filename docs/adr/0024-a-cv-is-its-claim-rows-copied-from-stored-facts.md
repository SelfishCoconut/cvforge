# 0024. A CV is its claim rows, each copied from a stored fact

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

Invariant 5: automatic-mode CV generation never emits a claim without a stored assertion,
enforced by the validator and tests, not by prompt wording. A CV that is free text with
claims attached afterwards can drift from them.

## Decision

**D-AD — the CV is the claim rows.** `cv_claim` holds every rendered string with its
section, item, slot and position; renderers read these rows and add nothing but template
structure (section titles). A string that is not a claim cannot be rendered. `entity_id` and
`assertion_id` are NOT NULL foreign keys, and `cv/store.py` (a registered writer for `cv` and
`cv_claim`, ADR-0011) refuses a claim whose assertion does not exist or is about another
entity.

**D-AE — a claim's text is copied from a fact, never written.** `cv/facts.py` is the one place
that turns a fact into a claim: the entity's name (bound to the assertion of its existence),
its summary (the assertion of `summary`) or a period from its dates (the assertion of its start
date). No assertion for a fact means no claim. Dates render as `YYYY-MM to YYYY-MM`, `from
YYYY-MM` or a single month; an unstated end date is never rendered as "present".

**D-AE2 — the assertion must state the claim, not merely exist.** An assertion records the value
it asserted (`value_json`). A claim is bound to the latest assertion of its field whose value *is*
the claim's text: the `name` assertion for a name (not the entity's bare existence), the `summary`
assertion for a summary, the start-date assertion for a period (and the end-date assertion too
whenever an end date is rendered). `cv/binding.claim_problem` enforces this in both the store
(before a claim is saved) and the validator (before presenting, finalising, sending or serving), so a
renamed entity invalidates the old text and a true-but-different assertion is refused
(`wrong_assertion`). Placing a claim under another entity's header (a role's organization,
a role's project) states a relationship, so it carries `link_assertion_id`, the existence
assertion of the edge between the two, or it is not emitted (`unlinked`).

**D-AF — selection follows the matches, not the requirements.** Automatic mode makes no model
call. It selects the confirmed entities backing `satisfied`/`evidenced` verdicts, then the
roles, projects and achievements that touch them (a project linked to a selected skill by
`used_in`/`demonstrates`, a role by `part_of`/`produced`/`involved`, with its organization via
`at_organization`), plus all confirmed education and credentials. A requirement's own words
are never rendered and `undocumented`/`gap` requirements select nothing.

**D-AG — validation recomputes from the live knowledge base.** `cv/validate.py` checks each
stored claim: its assertion exists and is about its entity, the entity is still `confirmed`,
and `claim_source` still yields exactly the stored text. Across claims it also flags (FR-29)
`overlapping_roles` (full-time roles whose recorded dates overlap; an open end runs to the
future), `inconsistent_period` (a skill's recorded use falls outside the recorded period of
what it was used in; the knowledge base holds no release dates, so this is the available
reading of "technology inconsistent with its period") and `incomplete_coverage` (a `required`
requirement the candidate is `satisfied` on has no claim on the CV). A CV with any issue cannot
be marked final (`finalize_cv`, the one sanctioned route to `final`), rendered, served from
`cv_out/` or recorded as sent: each of those re-validates against the live knowledge base. Versions are `max + 1` per posting with an
optional `parent_cv_id`.

## Consequences

- The automatic CV is plain and short: it can only be as rich as the stored summaries.
  Richer wording is collaborative mode (M6), which adds claims through the same table.
- A CV goes stale when knowledge changes; validation says so (`text_mismatch`,
  `inactive_entity`) instead of the CV silently keeping an outdated line.
- ADR-0023's notes apply: a stored match is a snapshot, so generation re-reads entity state.
