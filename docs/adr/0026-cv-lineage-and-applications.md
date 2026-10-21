# 0026. CV versions are per posting; only a final CV can be recorded as sent

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-27 asks for version history and parent links; FR-28 for tracking which CV went to which
posting. Both sit on the CV claims of ADR-0024, where a CV that has not validated must not be
presented.

## Decision

**D-AM — versions are `max + 1` per posting, parents must exist and share the posting.**
`save_cv` numbers a posting's CVs 1, 2, 3 under a unique `(job_posting_id, version)`. A parent
that does not exist is a 404; one that targets another posting is a 422 (`WrongPostingError`).
Because a parent must already exist, parent links cannot loop; `cv/versions.lineage` still
refuses a chain that does not end, so a tampered database cannot hang a request.

**D-AN — `application` links a posting and a CV, and is written by `cv/applications.py`**, a
registered writer (ADR-0011) of that one table. `status` is a closed set (`planned`, `applied`,
`interviewing`, `offer`, `rejected`, `withdrawn`) enforced by a CHECK constraint; `cv_id` is a
foreign key, so an application cannot reference a missing CV.

**D-AO — only a final CV targeting that posting can be recorded**, and any status beyond
`planned` needs `applied_at`. This is the place where "validate before presenting" (FR-29)
bites: a draft that never passed validation cannot become a sent application.

## Consequences

- Re-sending the same CV to the same posting records a second application; usage queries
  return both.
- Editing a CV (collaborative mode, M6) creates a child version; the lineage endpoint is how
  the UI will show it.
