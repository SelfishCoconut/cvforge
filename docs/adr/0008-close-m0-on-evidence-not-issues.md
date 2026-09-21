# 0008. M0 closes on evidenced requirements; unevidenced NFRs move to M1

Date: 2026-09-21
Status: accepted (decided by Claude under Álvaro's standing delegation of 2026-09-20; reported to him afterwards)

## Context

M0's epic, issue #1, carried seven non-functional requirements. It closed with PR #52. The
release skill's traceability audit then asked the question the issue state does not
answer: is each requirement *demonstrably* met, by a check that would fail if it broke?

- **NFR-03** (coverage floor) and **NFR-04** (mypy strict + xenon): met. They are enforced
  by `pyproject.toml` and required CI contexts.
- **NFR-06** (personal data never committed): criteria 1, 2 and 4 are met. Criterion 3 is
  false. The M0 plan at `0e66e75` contains the author's personal email once. The address
  has been gone from the tree since `22842e5`, and every commit's author metadata is the
  noreply address. Gitleaks scans for secrets, not personal data, so it did not flag it.
- **NFR-01** (local-first network audit): its enforcing test (`test_network_policy.py`)
  does not exist.
- **NFR-02** (localhost binding): its enforcing test (`test_app_bind.py`) does not exist.
- **NFR-08** (no live model calls in tests): its conftest check does not exist.
- **NFR-09** (single-file DB with export): its enforcing test (`test_db_export.py`) does
  not exist. NFR-09 could not have been met in M0 at all, because there is no database
  until M1.

The fact behind NFR-01, -02 and -08 is true today. There is no provider layer and no
outbound client, and the server binds `127.0.0.1`. But the tests are the requirement.
A property that holds only because nothing has been built yet is exactly the kind that
erodes silently when M1 adds an LLM client and a database.

## Decision

We will close M0 on what is evidenced, and move the rest explicitly:

- NFR-01, NFR-02, NFR-08 and NFR-09 change milestone to **M1**. Each is traced to its own
  issue (#59, #60, #61, #62). They land with the code that makes them testable: the
  provider layer, the app factory's bind configuration, the test harness for agents, and
  the database.
- NFR-03 and NFR-04 have their criteria ticked. NFR-06 has criteria 1, 2 and 4 ticked.
- NFR-06 criterion 2's wording is corrected from "a non-zero exit" to "a PreToolUse `deny`
  decision". A gating hook in this repo must exit 0 and fail open, so the old wording
  described a behaviour that would be a defect.
- NFR-06 criterion 3 stays **unticked** and is tracked as decision issue #64. Rewriting
  public history is Álvaro's call. Under `enforce_admins` it also requires lifting branch
  protection temporarily.

## Alternatives considered

- **Tick everything, because the properties currently hold.** Rejected. It would record
  as verified four requirements that no check verifies, and the first M1 PR would
  inherit a false baseline.
- **Hold M0 open and write the four tests now.** Rejected. NFR-09 needs the database, so
  M0 could not close until M1's first task anyway. The other three are cheapest to write
  alongside the code they guard, and writing them against a stub would test the stub.
- **Keep them in M0 and reopen #1.** Rejected. The release skill forbids closing a
  milestone with open issues, so M0 would stay open indefinitely for work that is M1's.

## Consequences

- M1 grows by four NFRs, all small and all testable once its first tasks land. The M1
  plan must schedule them.
- The v0.1.0 tag describes a foundation whose remaining guarantees are listed, not
  implied.
- NFR-06 has a known, recorded exception until #64 is decided.
