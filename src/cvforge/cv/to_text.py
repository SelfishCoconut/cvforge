"""Render a stored CV as plain text for applicant tracking systems (FR-26).

Generated from the claim rows, never scraped from the PDF: `pdftotext` output drifts with
typography, this does not. It carries exactly the claims the `.tex` carries.
"""

from cvforge.cv.store import StoredCv
from cvforge.kb.vocab import ClaimSlot


def render_text(cv: StoredCv) -> str:
    """Render `cv` as ATS-friendly plain text.

    Args:
        cv: The stored CV.

    Returns:
        The text, with one section per block and `-` bullets.
    """
    sections: dict[str, dict[int, dict[ClaimSlot, list[str]]]] = {}
    for claim in cv.claims:
        item = sections.setdefault(claim.section, {}).setdefault(claim.item_index, {})
        item.setdefault(claim.slot, []).append(claim.text)
    blocks: list[str] = []
    for title, items in sections.items():
        lines = [title.upper()]
        for index in sorted(items):
            slots = items[index]
            head = " - ".join(slots.get(ClaimSlot.HEADER, []) + slots.get(ClaimSlot.SUBHEADER, []))
            period = " ".join(slots.get(ClaimSlot.PERIOD, []))
            title_line = f"{head} ({period})" if head and period else head or period
            if title_line:
                lines.append(title_line)
            lines += [f"- {bullet}" for bullet in slots.get(ClaimSlot.BULLET, [])]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
