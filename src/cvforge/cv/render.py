"""Render a stored CV as LaTeX (FR-26).

Pure and deterministic: the same claims and template give the same bytes, with no model,
clock or randomness, so the output is snapshot-testable. Only claim text and section titles
reach the page, and all of it passes through `latex_escape`, because names and summaries are
user data that may contain `&`, `%`, `_` or `#`. The template (`templates/cv/`) carries
structure and typography, never facts.
"""

from pathlib import Path

from cvforge.cv.store import StoredCv
from cvforge.kb.vocab import ClaimSlot

TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "cv" / "classic.tex"
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    """Escape every character LaTeX treats specially.

    Args:
        text: Plain text from the knowledge base.

    Returns:
        Text that typesets literally. Newlines become spaces.
    """
    return "".join(_ESCAPES.get(ch, ch) for ch in " ".join(text.split()))


def _items(cv: StoredCv) -> dict[str, dict[int, list[tuple[ClaimSlot, str]]]]:
    sections: dict[str, dict[int, list[tuple[ClaimSlot, str]]]] = {}
    for claim in cv.claims:
        sections.setdefault(claim.section, {}).setdefault(claim.item_index, []).append(
            (claim.slot, latex_escape(claim.text))
        )
    return sections


def _item_tex(claims: list[tuple[ClaimSlot, str]]) -> list[str]:
    def pick(slot: ClaimSlot) -> list[str]:
        return [text for s, text in claims if s is slot]

    lines: list[str] = []
    header, sub, period = pick(ClaimSlot.HEADER), pick(ClaimSlot.SUBHEADER), pick(ClaimSlot.PERIOD)
    if header:
        title = rf"\textbf{{{header[0]}}}" + (rf", {sub[0]}" if sub else "")
        lines.append(rf"{title}\hfill {period[0] if period else ''}\par")
    bullets = pick(ClaimSlot.BULLET)
    if header and bullets:
        lines += [r"\begin{itemize}", *(rf"\item {b}" for b in bullets), r"\end{itemize}"]
    elif bullets:
        lines.append(", ".join(bullets) + r"\par")
    return lines


def render_tex(cv: StoredCv) -> str:
    """Render `cv` as a complete LaTeX document.

    Args:
        cv: The stored CV.

    Returns:
        The `.tex` source.
    """
    body: list[str] = []
    for title, items in _items(cv).items():
        body.append(rf"\section*{{{latex_escape(title)}}}")
        for index in sorted(items):
            body += _item_tex(items[index])
    return TEMPLATE.read_text(encoding="utf-8").replace("%%BODY%%", "\n".join(body))
