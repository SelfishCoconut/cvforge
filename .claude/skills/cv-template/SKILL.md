---
name: cv-template
description: Work on CV rendering — LaTeX templates, PDF compilation, the plain-text ATS rendering, claim traceability and CV validation. Use when changing templates/cv/, src/cvforge/cv/, or anything about how a CV is produced.
---

# CV rendering

Three artifacts per CV, all from the same stored facts: `.tex` (authored source),
`.pdf` (compiled), `.txt` (ATS-readable plain text, and the source for form
autofill). Paths are recorded on the `cv` row; files live under `cv_out/`, which
is gitignored.

## The rule that governs everything here

**Every claim in a generated CV traces to a stored assertion.** In automatic mode
the generator may not invent a skill, a responsibility, an achievement, a date or a
metric — not even a plausible rewording that adds meaning. Each rendered bullet
gets a `cv_claim` row naming the entity and assertion behind it, and
`cv/validate.py` rejects a CV with an unsupported claim.

A requirement matched only as `undocumented` or `gap` must **not** appear. If the
phrasing feels thin, the fix is a discovery question (collaborative mode), not a
richer adjective.

## Layout

- `templates/cv/` — LaTeX templates. Structure and typography only; no facts.
- `src/cvforge/cv/render.py` — facts + template → `.tex`. Pure and deterministic;
  no model call, no clock, no randomness, so it is snapshot-testable.
- `src/cvforge/cv/compile.py` — `.tex` → `.pdf` via `latexmk`. The only place that
  shells out; fail loudly with the LaTeX log on a non-zero exit.
- `src/cvforge/cv/to_text.py` — structured CV → plain text. Derived from the same
  model as the `.tex`, never scraped out of the PDF.
- `src/cvforge/cv/validate.py` — claim support, internal contradictions, date and
  technology consistency, coverage of the posting's important requirements (FR-29).
- `src/cvforge/cv/versions.py` — version chain, parent links, job linkage.

## Rules

- **Escape everything that comes from the knowledge base.** Names and summaries are
  user data containing `&`, `%`, `_`, `#`. Unescaped, they break the build or
  silently change the output. Escaping lives in one helper with its own tests.
- **Rendering stays deterministic.** Same facts plus same template equals the same
  bytes, or the golden suite is worthless.
- **Plain text is generated, not extracted.** `pdftotext` output drifts with
  typography; the ATS rendering must be stable.
- **Never commit a rendered CV.** `data/` and `cv_out/` are gitignored and the
  `guard-private-data` hook blocks it. Test fixtures use a synthetic profile.
- **A new section means a new `cv_claim` mapping.** A section rendering text that
  no claim covers is exactly the hole this design exists to prevent.
