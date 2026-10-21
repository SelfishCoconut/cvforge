# 0025. CV rendering is claim rows in a fixed template, compiled by latexmk

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-26 needs `.tex`, `.pdf` and an ATS plain-text rendering of the same CV (spec D11), with
no corrupt output and nothing written into the repository.

## Decision

**D-AH — one template, claims only.** `templates/cv/classic.tex` (base LaTeX packages only) holds structure and
typography with a single `%%BODY%%` slot. `cv/render.py` fills it from the stored claim rows
and nothing else: section titles are template structure, every other string is a claim.
Rendering is a pure function of the claims and the template (no model, clock or randomness).

**D-AI — one escape helper.** Every claim and title passes through `latex_escape` (backslash,
`& % $ # _ { } ~ ^`, newlines folded to spaces); it has its own tests, because names and
summaries are user data.

**D-AJ — the plain text is generated, not extracted.** `cv/to_text.py` renders from the same
rows (`SECTION` heading, `Header - Subheader (period)`, `-` bullets), so it carries exactly the
claims the `.tex` does and does not drift with typography.

**D-AK — `latexmk` is the only shell-out, and it fails loudly.** `cv/compile.py` runs it
with a fixed argv (no shell), `-halt-on-error`, a 120 s timeout. A missing tool, a timeout, a
non-zero exit or an empty PDF is a `CompileError` carrying the tail of the LaTeX log; the API
answers 502 and records no artifact paths.

**D-AL — only a valid CV is rendered, into `cv_out/`.** `POST /api/cvs/{id}/render` runs the
validator first (409 on any issue) and writes `cv.tex`, `cv.txt`, `cv.pdf` under
`<cv_out_dir>/cv-<id>/` (default `cv_out/`, gitignored). Paths are recorded on the `cv` row
after a successful compile.

## Consequences

- CI installs a minimal TeX Live (`latexmk`, `texlive-latex-base/-recommended`,
  `texlive-fonts-recommended`; the template needs nothing from `-extra`) for the integration and demo jobs, a minute or two per run.
- The default template is plain on purpose; more templates are a `templates/cv/` addition.
- A failed compile can leave `cv.tex` and `cv.txt` on disk without a recorded PDF path.
