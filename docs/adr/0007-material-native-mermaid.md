# 0007. Mermaid renders through Material's native support, not mkdocs-mermaid2

Date: 2026-09-20
Status: accepted

## Context

`Docs build` is about to become one of eleven required status checks on a
protected `main`. A required check has to be deterministic; if it can fail on
input that did not change, it stops being a gate and becomes a coin toss that
blocks merges.

`mkdocs-mermaid2-plugin` is not deterministic. Read out of the installed
package rather than inferred:

- `mermaid2/plugin.py:141` calls `url_exists(javascript, ...)` on every build,
  where `javascript` defaults to
  `https://unpkg.com/mermaid@<ver>/dist/mermaid.esm.min.mjs`.
- `mermaid2/util.py:81-85` implements that with `requests.get(url)` — a live
  network call during `mkdocs build`. On a `RequestException` it emits a real
  mkdocs **warning**, which `--strict` turns into an abort. On a reachable but
  non-200 response it returns `False`, and `plugin.py:143` raises
  `FileNotFoundError`, crashing the build outright.

So unpkg.com's availability could turn a merge gate red two different ways with
no code change. This was observed once in CI ("Aborted with 1 warnings in strict
mode!" on an unchanged docs tree, green on rerun) before it was traced to
source. It also contradicts the project's local-first premise: `mkdocs build`
could not run offline.

## Decision

Drop the `mermaid2` plugin. Render Mermaid through Material for MkDocs' native
support: a `pymdownx.superfences` custom fence using
`pymdownx.superfences.fence_code_format`, which emits `<div class="mermaid">`
and lets the theme load Mermaid in the browser.

```yaml
markdown_extensions:
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
```

The authored diagrams themselves do not change. They stay Mermaid fences inside
`docs/architecture/` markdown, exactly as CLAUDE.md requires.

## Alternatives considered

**Vendor `mermaid.esm.min.mjs` and point the plugin's `javascript:` option at
the local copy.** This does work — a non-`http` value routes `url_exists` to its
`os.path.exists` branch and makes zero network calls. Rejected because it commits
roughly 3 MB of minified third-party JavaScript to a public repository, requires
widening pre-commit's `check-added-large-files` threshold for it, and leaves the
project owning a vendored dependency it must remember to update.

**Accept the flake and re-run.** Rejected. A required context that randomly
blocks merges is the exact failure mode branch protection is meant to prevent,
and the cost lands on every future PR.

## Consequences

- Build-time network calls from the docs build: none. `mkdocs build --strict`
  now runs offline, which the local-first premise always implied it should.
- One fewer plugin. Material's standing notice is that MkDocs 2.0 removes the
  plugin system entirely; this build went from three plugins to two, so the
  eventual migration is smaller.
- Mermaid is fetched by the browser when a diagram page is opened, not by CI.
  Diagram rendering is therefore no longer coupled to the merge gate at all —
  a broken diagram is a visible bug on a page, not a red required check.
- Verified before adoption: `mkdocs build --strict` exits 0; both diagram pages
  emit `class="mermaid"` divs; `grep unpkg` over the generated site returns
  nothing.
- The Mermaid version is whatever Material ships rather than a version this
  repository pins. Accepted: the diagrams use basic C4, ER and flowchart syntax,
  and ADR-0005's pinning policy is about code that runs with a token, not about
  a renderer for four static diagrams.
