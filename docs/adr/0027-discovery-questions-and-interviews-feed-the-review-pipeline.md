# 0027. Discovery questions and interviews feed the review pipeline

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

`undocumented` requirements are plausibly true but unrecorded (ADR-0023). FR-30 asks the system
to ask about them; FR-32 adds an interview mode that probes undocumented and gap requirements.
Whatever the user answers must reach the knowledge base only through the review pipeline
(invariants 1 and 4).

## Decision

**D-AP — questions are derived, not generated.** `discovery/questions.py` builds each question from
the requirement's own text and the stored verdict's rationale; no model is involved. A discovery
question exists only for an `undocumented` requirement; a `gap` is left to the learning planner
(M7). An interview also covers `gap` requirements, because a recorded gap can be out of date.

**D-AQ — an answer is a chat message in disguise.** Answering stores the user's words as
`message` evidence in a conversation source, runs the same read-only-tool ingest agent as chat
(the question is fenced as data, since it embeds untrusted posting text) and records a pending
proposal (origin `chat`). Declining writes nothing. A blank answer is refused.

**D-AR — an interview is one proposal of origin `interview`.** The transcript's non-blank
answers are stored as one evidence span in a conversation source labelled "interview for posting
N"; the interview agent (same tools, its own prompt) reads the fenced Q&A, and only *answers* may
state facts. A transcript with no substantive answer records nothing and calls no model. Answers
to requirements that were not asked about are refused (422).

## Consequences

- One evidence span per interview is coarse: a fact cites the whole answers block, not one answer.
  Per-turn evidence needs per-turn proposals or a multi-evidence payload, a later refinement.
- Questions follow the stored matches; after new knowledge is committed, re-running the match
  refreshes which requirements still call for a question.
