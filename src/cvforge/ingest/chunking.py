"""Split page text into windows small enough for a local model's context (FR-15).

Ollama's default context window is 4096 tokens (#123), shared by the prompt, the tool
schemas and the model's reasoning, so a page is never sent whole.
"""

from dataclasses import dataclass

DEFAULT_MAX_CHARS = 3000


@dataclass(frozen=True)
class Chunk:
    """A window of one page.

    Attributes:
        page: 1-based page number.
        offset: Where `text` begins within the page text.
        text: The window; it is exactly ``page_text[offset : offset + len(text)]``.
    """

    page: int
    offset: int
    text: str


def chunk_pages(pages: tuple[str, ...], *, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Split `pages` into chunks of at most `max_chars`, breaking on paragraphs.

    Args:
        pages: The page texts.
        max_chars: The most characters in one chunk.

    Returns:
        The chunks in document order. Blank pages produce none. A paragraph longer
        than `max_chars` is cut at the limit.
    """
    chunks: list[Chunk] = []
    for number, text in enumerate(pages, start=1):
        if text.strip():
            chunks.extend(_chunk_page(number, text, max_chars))
    return chunks


def _paragraph_spans(text: str, max_chars: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for part in text.split("\n\n"):
        end = start + len(part)
        if part.strip():
            for cut in range(start, end, max_chars):
                spans.append((cut, min(cut + max_chars, end)))
        start = end + 2
    return spans


def _chunk_page(page: int, text: str, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: tuple[int, int] | None = None
    for start, end in _paragraph_spans(text, max_chars):
        if current is not None and end - current[0] <= max_chars:
            current = (current[0], end)
            continue
        if current is not None:
            chunks.append(Chunk(page, current[0], text[current[0] : current[1]]))
        current = (start, end)
    if current is not None:
        chunks.append(Chunk(page, current[0], text[current[0] : current[1]]))
    return chunks
