# 0005. Third-party Actions that receive a token are pinned by commit digest

Date: 2026-09-19
Status: accepted

## Context

The CI and Security workflows call actions published by three parties: GitHub
itself (`actions/checkout`, `github/codeql-action/*`), and two third parties
(`astral-sh/setup-uv`, `gitleaks/gitleaks-action`).

A version tag is mutable. Its owner can re-point it at any commit, and the next
workflow run executes that new code with whatever permissions the step was
granted. `gitleaks/gitleaks-action` is handed `GITHUB_TOKEN` explicitly. A
re-pointed tag there would run attacker-controlled code holding a repository
token — and the hole would sit inside the workflow whose job is to detect
exactly that class of problem.

## Decision

Pin a third-party action by full commit SHA, with a `# vX.Y.Z` comment, when it
receives a token. Otherwise a major version tag is sufficient.

Concretely:

- `gitleaks/gitleaks-action` — **pinned by digest**. It receives `GITHUB_TOKEN`.
- `astral-sh/setup-uv` — major tag. It receives no token.
- `actions/*` and `github/codeql-action/*` — major tags. These are published by
  the same vendor that operates the runner, so a digest pin buys little against
  that threat model.

Resolve the digest with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`,
which dereferences an annotated tag to the commit. A tag-object SHA does not work
as an Actions pin.

The `github-actions` ecosystem in `dependabot.yml` keeps pins current, so this
carries no standing maintenance cost.

## Alternatives considered

- **Pin everything by digest.** The strictest policy and defensible. Rejected as
  the wrong trade here: it would churn an already-green CI workflow for no gain
  against a threat model where GitHub is already trusted to run the job at all,
  and every unnecessary pin is another Dependabot PR competing for attention with
  the ones that matter.
- **Pin nothing; rely on Dependabot.** Dependabot proposes upgrades; it does not
  protect against a tag being re-pointed under an unchanged version, which is
  precisely the attack.
- **Drop the gitleaks step.** Removing a secret scanner to avoid a supply-chain
  question makes the repository less safe, not more.

## Consequences

- Upgrading a pinned action is a Dependabot PR that changes an opaque SHA. The
  `# vX.Y.Z` comment is what makes that diff reviewable, so it is not optional.
- The justification for leaving `setup-uv` unpinned is **"it receives no
  token"** — *not* "it cannot execute code". It does run arbitrary code on a
  runner that then runs `uv sync` against fork-supplied `pyproject.toml`. The
  blast radius is an ephemeral runner holding a read-only token, which is
  acceptable; the reasoning must be stated accurately so the exception is not
  widened later on a false premise.
- The policy is stated in terms of *token exposure*, so it re-decides itself
  correctly: if a currently-unpinned action is ever given a token, it must be
  pinned in the same change.
