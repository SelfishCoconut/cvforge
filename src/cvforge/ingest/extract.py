"""Extract a stored document into one reviewable proposal with cited spans (FR-15).

The agent reads one chunk at a time and quotes each fact's passage. This module finds
every quote in the stored page text and builds the evidence locator itself
(`ingest.locators`); a fact whose quote is not in the document has no evidence and is
dropped, so nothing is proposed without a citation (invariant 3). Everything lands in
a pending proposal; nothing reaches the knowledge base unreviewed (invariant 4).
"""

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from pydantic_ai.models import Model

from cvforge.ingest.chunking import DEFAULT_MAX_CHARS, Chunk, chunk_pages
from cvforge.ingest.documents import PAGE_SEPARATOR
from cvforge.ingest.locators import Span, format_locator, resolve_excerpt
from cvforge.kb import apply, intake, queries
from cvforge.kb.classify import SimilarFinder
from cvforge.kb.models import normalize_name
from cvforge.kb.vocab import Origin, SourceKind
from cvforge.llm.agents.document import build_document_agent
from cvforge.llm.convert import RejectedItem, to_payloads
from cvforge.llm.schemas import DocumentEdge, DocumentFact, DocumentResult
from cvforge.llm.tools import KbDeps

Item = DocumentFact | DocumentEdge


@dataclass(frozen=True)
class Extraction:
    """The outcome of extracting one document.

    Attributes:
        proposal_id: The pending proposal, or None when nothing was extracted.
        similarity_available: False if duplicate detection could not run.
        rejected: Items the agent produced that were dropped, with the reason.
        chunks: How many chunks the document was read in.
    """

    proposal_id: int | None
    similarity_available: bool
    rejected: list[RejectedItem]
    chunks: int


def extract_document(
    engine: sa.Engine,
    source_id: int,
    *,
    model: Model,
    deps: KbDeps | None = None,
    similar: SimilarFinder | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Extraction:
    """Read a stored document with the document agent and record a pending proposal.

    Args:
        engine: The knowledge-base engine.
        source_id: A `document` source whose extracted text is on disk.
        model: The model to run the agent against.
        deps: What the agent's read-only tools may read; defaults to `engine` alone.
        similar: Optional similarity lookup for duplicate detection.
        max_chars: The most characters of a page shown to the model at once.

    Returns:
        The proposal id (or None), and what was dropped.

    Raises:
        NotFoundError: If `source_id` is not a document source with readable text.
    """
    pages = _load_pages(engine, source_id)
    chunks = chunk_pages(pages, max_chars=max_chars)
    agent = build_document_agent(model)
    tool_deps = deps or KbDeps(engine, None)
    merged = _Merged(pages)
    for number, chunk in enumerate(chunks):
        result = agent.run_sync(_prompt(chunk), deps=tool_deps).output
        merged.add(f"c{number}:", chunk, result)
    cited: dict[Span, int] = {}

    def evidence_for(item: object) -> int | None:
        span = merged.spans.get(id(item))
        if span is None:
            return None
        if span not in cited:
            excerpt = pages[span.page - 1][span.start : span.end]
            cited[span] = apply.record_evidence(engine, source_id, format_locator(span), excerpt)
        return cited[span]

    converted = to_payloads(merged.result(), evidence_id=evidence_for)
    label = _label(engine, source_id)
    stored = intake.propose(
        engine,
        origin=Origin.DOCUMENT,
        source_id=source_id,
        summary=f"Facts from {label}"[:200],
        payloads=converted.payloads,
        similar=similar,
    )
    return Extraction(
        proposal_id=stored.proposal_id if stored else None,
        similarity_available=stored.similarity_available if stored else True,
        rejected=converted.rejected,
        chunks=len(chunks),
    )


def _label(engine: sa.Engine, source_id: int) -> str:
    with engine.connect() as conn:
        source = queries.get_source(conn, source_id)
    return source.label if source else "document"


def _load_pages(engine: sa.Engine, source_id: int) -> tuple[str, ...]:
    with engine.connect() as conn:
        source = queries.get_source(conn, source_id)
    if source is None or source.kind != SourceKind.DOCUMENT.value:
        raise apply.NotFoundError(f"document {source_id} does not exist")
    path = Path(source.raw_text_path) if source.raw_text_path else None
    if path is None or not path.is_file():
        raise apply.NotFoundError(f"the extracted text of document {source_id} is not on disk")
    return tuple(path.read_text(encoding="utf-8").split(PAGE_SEPARATOR))


def _prompt(chunk: Chunk) -> str:
    # The document is data. Neutralise a closing tag so it cannot end the data early.
    text = chunk.text.replace("</document>", "</ document>")
    return f"Page {chunk.page} of an uploaded document.\n\n<document>\n{text}\n</document>"


class _Merged:
    """Accumulates the agent's per-chunk results into one, resolving each item's span.

    Local ids are prefixed per chunk so two chunks cannot collide, and a fact that
    repeats an earlier one (same kind and normalised name) is folded into it.
    """

    def __init__(self, pages: tuple[str, ...]) -> None:
        self._pages = pages
        self._facts: list[DocumentFact] = []
        self._edges: list[DocumentEdge] = []
        self._by_name: dict[tuple[str, str], str] = {}
        self._seen_edges: set[tuple[str | int, str, str | int]] = set()
        self.spans: dict[int, Span | None] = {}

    def add(self, prefix: str, chunk: Chunk, result: DocumentResult) -> None:
        """Fold one chunk's result in."""
        ids: dict[str, str] = {}
        for fact in result.facts:
            key = (fact.kind.value, normalize_name(fact.name))
            if key in self._by_name:
                ids[fact.local_id] = self._by_name[key]
                continue
            renamed = fact.model_copy(update={"local_id": prefix + fact.local_id})
            ids[fact.local_id] = renamed.local_id
            self._by_name[key] = renamed.local_id
            self._facts.append(renamed)
            self._locate(renamed, chunk)
        for edge in result.edges:
            src, dst = _remap(edge.src, ids, prefix), _remap(edge.dst, ids, prefix)
            if (src, edge.rel.value, dst) in self._seen_edges:
                continue
            self._seen_edges.add((src, edge.rel.value, dst))
            renamed_edge = edge.model_copy(update={"src": src, "dst": dst})
            self._edges.append(renamed_edge)
            self._locate(renamed_edge, chunk)

    def _locate(self, item: Item, chunk: Chunk) -> None:
        self.spans[id(item)] = resolve_excerpt(
            self._pages, page=chunk.page, excerpt=item.excerpt, hint=chunk.offset
        )

    def result(self) -> DocumentResult:
        """Return everything accumulated as one result."""
        return DocumentResult(facts=self._facts, edges=self._edges)


def _remap(end: str | int, ids: dict[str, str], prefix: str) -> str | int:
    if isinstance(end, int):
        return end
    return ids.get(end, prefix + end)
