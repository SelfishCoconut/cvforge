"""Document upload: store the file privately and extract its text (FR-14).

Uploading records where the text came from (a `document` source) and nothing else.
No entity, edge or proposal is created here; extraction of facts is FR-15 and
every fact still goes through review (invariant 4).
"""

import logging
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from cvforge.api.chat import (
    Embedder,
    Factory,
    ProposalView,
    RejectedView,
    proposal_view,
)
from cvforge.api.errors import engine
from cvforge.ingest.documents import (
    MAX_UPLOAD_BYTES,
    ExtractionError,
    UnsupportedFormatError,
    extract_text,
    store_document,
)
from cvforge.ingest.extract import extract_document
from cvforge.kb import apply
from cvforge.kb.dedup import make_similar_finder
from cvforge.kb.vocab import SourceKind
from cvforge.llm.settings_store import load_settings
from cvforge.llm.tools import KbDeps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])
Engine = Annotated[sa.Engine, Depends(engine)]


class DocumentView(BaseModel):
    """The result of an upload.

    Attributes:
        source_id: The `document` source recorded for it.
        filename: The name it was uploaded under.
        pages: How many pages of text were extracted.
        characters: Total extracted characters.
    """

    source_id: int
    filename: str
    pages: int
    characters: int


@router.post("/documents", status_code=201)
async def upload_document(db: Engine, request: Request, file: UploadFile) -> DocumentView:
    """Accept a PDF, DOCX, Markdown or plain-text file and extract its text.

    The extension is checked before any byte is parsed; a corrupt file is refused
    before anything is stored.

    Args:
        db: The knowledge-base engine.
        request: The request, for the configured data directory.
        file: The uploaded file.

    Returns:
        The recorded source and the size of the extracted text.

    Raises:
        HTTPException: 413 above 20 MiB, 415 for an unsupported format, 422 for a
            corrupt file or one with no text.
    """
    filename = file.filename or "upload"
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"the file is larger than {MAX_UPLOAD_BYTES // 2**20} MiB")
    try:
        document = await run_in_threadpool(extract_text, filename, data)
    except UnsupportedFormatError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc
    stored = await run_in_threadpool(
        store_document, request.app.state.settings.data_dir, filename, data, document
    )
    source_id = apply.record_source(
        db,
        SourceKind.DOCUMENT,
        filename,
        uri=str(stored.original),
        content_hash=stored.sha256,
        raw_text_path=str(stored.text),
    )
    return DocumentView(
        source_id=source_id,
        filename=filename,
        pages=len(document.pages),
        characters=len(document.text),
    )


class ExtractionView(BaseModel):
    """The result of extracting a document.

    Attributes:
        source_id: The document.
        chunks: How many chunks it was read in.
        proposal: The pending proposal; empty when nothing was extracted.
        rejected: What the agent produced that was dropped, and why.
        similarity_available: False if duplicate detection could not run.
    """

    source_id: int
    chunks: int
    proposal: ProposalView
    rejected: list[RejectedView]
    similarity_available: bool


@router.post("/documents/{source_id}/extract")
def extract(
    source_id: int, db: Engine, embedder: Embedder, model_factory: Factory
) -> ExtractionView:
    """Read an uploaded document with the model and record a pending proposal.

    Every fact carries the passage that states it; a fact whose passage cannot be
    found in the document is dropped. Nothing is written to the knowledge base until
    the proposal is reviewed and committed.

    Args:
        db: The knowledge-base engine.
        source_id: A document source id from `POST /api/documents`.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.

    Returns:
        The proposal and anything dropped.

    Raises:
        HTTPException: 404 for an unknown document; 502 if the model fails.
    """
    finder = (
        make_similar_finder(db, embedder, load_settings(db).similarity_threshold)
        if embedder is not None
        else None
    )
    try:
        outcome = extract_document(
            db,
            source_id,
            model=model_factory(db),
            deps=KbDeps(db, embedder),
            similar=finder,
        )
    except apply.NotFoundError:
        raise
    except Exception as exc:
        logger.warning("document extraction failed: %s", exc)
        raise HTTPException(502, f"the model could not process the document: {exc}") from exc
    return ExtractionView(
        source_id=source_id,
        chunks=outcome.chunks,
        proposal=proposal_view(db, outcome.proposal_id),
        rejected=[RejectedView(item=r.item, reason=r.reason) for r in outcome.rejected],
        similarity_available=outcome.similarity_available,
    )
