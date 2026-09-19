---
name: docs
description: Build, serve or extend the CVForge documentation site (MkDocs Material + mkdocstrings). Use for "build the docs", "add a docs page", "the docs build is failing", or docs drift checks.
---

# Documentation site (docs-as-code)

Principle: anything derivable from code is generated at build time. Anything that
expresses intent is authored and reviewed.

## Build

- `make docs` → `mkdocs build --strict`. Strict mode fails on any broken internal
  link or unresolved mkdocstrings reference. This is the required CI check named
  **`Docs build`** — fix the link or the docstring; never relax `--strict` to make
  a build pass, in CI or locally.
- `make docs-serve` → live preview.
- `mkdocs.yml` sets `exclude_docs: superpowers/`: the plans and specs under
  `docs/superpowers/` are working documents, not site pages, and they contain
  relative links (to each other, to sibling working files) that would otherwise
  fail `--strict`. Do not remove that exclusion to "fix" a link inside
  `docs/superpowers/` — exclude it, don't chase it.

## What goes where

- **Generated**: `docs/reference/*.md` hold only mkdocstrings directives
  (`::: cvforge.<module>`). The docstring *is* the documentation — to change the
  page, change the docstring.
- **Authored**: `docs/architecture/` — C4 context/container, the knowledge-model
  ER diagram, and the write-path flow, as Mermaid in markdown. Diffable in PRs and
  rendered natively by GitHub.
- **Authored**: `docs/requirements/srs.md` (owned by the `requirements` skill),
  `docs/adr/` (owned by the `adr` skill).

## Rules

- **There is no auto-generated UML** (decision D7). Do not add pyreverse, a layer
  map, or a diagram-generation script — that machinery was a CI liability in the
  previous project.
- New public symbol → Google-style docstring; it renders straight into the site.
- A code change that alters a flow an authored diagram depicts must update that
  diagram **in the same PR**. The `doc-curator` agent checks this.
- Adding a page or an ADR means adding it to `nav` in `mkdocs.yml`, or the strict
  build fails on an orphan file.
