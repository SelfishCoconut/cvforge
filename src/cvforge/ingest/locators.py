"""Turn a quoted excerpt into a stable evidence locator (FR-15).

A model is good at quoting and bad at counting characters, so it never supplies a
character range. It quotes the passage and names the page; the server finds the quote
in the stored page text and builds the locator itself. A locator therefore always
reproduces its excerpt when sliced from that text, and a quote that is not in the
document has no locator and is dropped (invariant 3).
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A character range within one page of a document.

    Attributes:
        page: 1-based page number.
        start: Start offset within the page text.
        end: End offset (exclusive) within the page text.
    """

    page: int
    start: int
    end: int


def format_locator(span: Span) -> str:
    """Format `span` as the locator stored on an evidence row, e.g. ``page:2 chars:10-80``."""
    return f"page:{span.page} chars:{span.start}-{span.end}"


def resolve_excerpt(
    pages: tuple[str, ...], *, page: int, excerpt: str, hint: int = 0
) -> Span | None:
    """Find `excerpt` in page `page` of `pages`.

    Matching is case-sensitive and ignores differences in whitespace, so a model that
    re-wraps a quote still resolves, to the original text.

    Args:
        pages: The stored page texts.
        page: 1-based page number the model named.
        excerpt: The quoted passage.
        hint: Prefer the first occurrence at or after this offset (where the chunk
            the model was shown begins); falls back to the first occurrence.

    Returns:
        The span, or None if the page does not exist or the quote is not in it.
    """
    words = excerpt.split()
    if not words or not 1 <= page <= len(pages):
        return None
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    matches = list(pattern.finditer(pages[page - 1]))
    if not matches:
        return None
    chosen = next((m for m in matches if m.start() >= hint), matches[0])
    return Span(page, chosen.start(), chosen.end())
