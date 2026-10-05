"""Chat intake: a free-text statement becomes a reviewable proposal (FR-11, FR-12).

There is no field on this endpoint that applies anything. The message is stored
as provenance, the agent reads it as data, and whatever it extracts is only ever
recorded as a pending proposal (invariant 4).
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from pydantic_ai.models import Model

from cvforge.api.errors import engine
from cvforge.kb import apply, intake, queries
from cvforge.kb.dedup import make_similar_finder
from cvforge.kb.embeddings import EmbeddingProvider
from cvforge.kb.vocab import Origin, SourceKind
from cvforge.llm.agents.ingest import build_ingest_agent
from cvforge.llm.convert import to_payloads
from cvforge.llm.schemas import IngestResult
from cvforge.llm.settings_store import load_settings
from cvforge.llm.tools import KbDeps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
Engine = Annotated[sa.Engine, Depends(engine)]

MAX_MESSAGE_CHARS = 20_000
ModelFactory = Callable[[sa.Engine], Model]


class ChatRequest(BaseModel):
    """One user message. The text is stored literally, not trimmed.

    Attributes:
        conversation_id: An existing conversation to continue; a new one when omitted.
        text: The message, 1 to 20 000 characters, not blank.
    """

    model_config = ConfigDict(extra="forbid")

    conversation_id: int | None = None
    text: str = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain a non-whitespace character")
        return value


class ProposedOperation(BaseModel):
    """One pending operation of the stored proposal.

    Attributes:
        id: The operation id, as used by the review endpoints.
        seq: Its position in the proposal.
        op_type: The operation type.
        payload: The typed payload as stored.
        classification: `new`, `known`, `duplicate` or `conflict`.
        target_kind: What it refers to, unless `new`.
        target_id: The id of that target, unless `new`.
    """

    id: int
    seq: int
    op_type: str
    payload: JsonValue
    classification: str
    target_kind: str | None
    target_id: int | None


class ProposalView(BaseModel):
    """The proposal a message produced; `id` is None when it produced nothing."""

    id: int | None
    operations: list[ProposedOperation]


class RejectedView(BaseModel):
    """Something the agent produced that could not become an operation."""

    item: str
    reason: str


class ChatResponse(BaseModel):
    """What the user sees after sending a message.

    Attributes:
        conversation_id: The conversation (a `source` id) the message belongs to.
        message_id: The evidence id of the stored message.
        reply: The agent's acknowledgement.
        proposal: The pending proposal, if any.
        rejected: Agent output that was dropped, and why.
        similarity_available: False when duplicate detection could not run.
    """

    conversation_id: int
    message_id: int
    reply: str
    proposal: ProposalView
    rejected: list[RejectedView]
    similarity_available: bool


def _embedder(request: Request) -> EmbeddingProvider | None:
    result: EmbeddingProvider | None = request.app.state.embedder
    return result


def _model_factory(request: Request) -> ModelFactory:
    result: ModelFactory = request.app.state.model_factory
    return result


Embedder = Annotated[EmbeddingProvider | None, Depends(_embedder)]
Factory = Annotated[ModelFactory, Depends(_model_factory)]


def _store_message(db: sa.Engine, body: ChatRequest) -> tuple[int, int]:
    """Record the message as provenance; returns (conversation id, evidence id)."""
    if body.conversation_id is None:
        conversation = apply.record_source(db, SourceKind.CONVERSATION, "chat conversation")
        number = 0
    else:
        conversation = body.conversation_id
        with db.connect() as conn:
            count = queries.message_count(conn, conversation)
        if count is None:
            raise HTTPException(404, f"conversation {conversation} does not exist")
        number = count
    evidence = apply.record_evidence(db, conversation, f"message:{number + 1}", body.text)
    return conversation, evidence


def _view(db: sa.Engine, proposal_id: int | None) -> ProposalView:
    if proposal_id is None:
        return ProposalView(id=None, operations=[])
    with db.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    if record is None:
        raise apply.NotFoundError(f"proposal {proposal_id} vanished")
    return ProposalView(
        id=record.id,
        operations=[
            ProposedOperation(
                id=op.id,
                seq=op.seq,
                op_type=op.op_type,
                payload=op.payload,
                classification=op.classification,
                target_kind=op.target_kind,
                target_id=op.target_id,
            )
            for op in record.operations
        ],
    )


def _finish(
    db: sa.Engine,
    embedder: EmbeddingProvider | None,
    conversation: int,
    evidence: int,
    result: IngestResult,
) -> ChatResponse:
    """Convert the agent's result and store it as a pending proposal (shared by both routes)."""
    converted = to_payloads(result, evidence_id=evidence)
    finder = (
        make_similar_finder(db, embedder, load_settings(db).similarity_threshold)
        if embedder is not None
        else None
    )
    stored = intake.propose(
        db,
        origin=Origin.CHAT,
        source_id=conversation,
        summary=result.reply[:200] or "chat message",
        payloads=converted.payloads,
        similar=finder,
    )
    return ChatResponse(
        conversation_id=conversation,
        message_id=evidence,
        reply=result.reply,
        proposal=_view(db, stored.proposal_id if stored else None),
        rejected=[RejectedView(item=r.item, reason=r.reason) for r in converted.rejected],
        similarity_available=stored.similarity_available if stored else embedder is not None,
    )


@router.post("/chat/messages")
def post_message(
    db: Engine, body: ChatRequest, embedder: Embedder, model_factory: Factory
) -> ChatResponse:
    """Store a message, extract facts from it, and record them as a pending proposal.

    The message is written as provenance before the model runs; a model failure
    afterwards leaves the message and no proposal.

    Args:
        db: The knowledge-base engine.
        body: The message.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.

    Returns:
        The reply, the pending proposal and anything the agent produced that was dropped.

    Raises:
        HTTPException: 404 for an unknown conversation; 502 if the model fails.
    """
    conversation, evidence = _store_message(db, body)
    try:
        agent = build_ingest_agent(model_factory(db))
        result = agent.run_sync(body.text, deps=KbDeps(db, embedder)).output
    except Exception as exc:
        logger.warning("ingest agent failed: %s", exc)
        raise HTTPException(502, f"the model could not process the message: {exc}") from exc
    return _finish(db, embedder, conversation, evidence, result)


def _line(event: dict[str, object]) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


async def _produce(
    queue: asyncio.Queue[str | None],
    db: sa.Engine,
    embedder: EmbeddingProvider | None,
    model_factory: ModelFactory,
    text: str,
    conversation: int,
    evidence: int,
) -> None:
    """Run the agent, putting NDJSON lines on `queue`; `None` marks the end."""
    try:
        agent = build_ingest_agent(model_factory(db))
        sent = ""
        async with agent.run_stream(text, deps=KbDeps(db, embedder)) as run:
            async for partial in run.stream_output(debounce_by=None):
                if partial.reply.startswith(sent) and len(partial.reply) > len(sent):
                    await queue.put(_line({"type": "delta", "text": partial.reply[len(sent) :]}))
                    sent = partial.reply
            result = await run.get_output()
        if result.reply.startswith(sent) and len(result.reply) > len(sent):
            await queue.put(_line({"type": "delta", "text": result.reply[len(sent) :]}))
        response = await run_in_threadpool(_finish, db, embedder, conversation, evidence, result)
        await queue.put(_line({"type": "proposal", **response.model_dump(exclude={"reply"})}))
        await queue.put(_line({"type": "done"}))
    except Exception as exc:
        logger.warning("ingest stream failed: %s", exc)
        message = f"the model could not process the message: {exc}"
        await queue.put(_line({"type": "error", "message": message}))
    finally:
        await queue.put(None)


async def stream_events(
    db: sa.Engine,
    embedder: EmbeddingProvider | None,
    model_factory: ModelFactory,
    text: str,
    conversation: int,
    evidence: int,
) -> AsyncGenerator[str]:
    """Yield NDJSON lines: `delta`s of the reply, then `proposal`, then `done`.

    Any failure yields one `error` event and ends the stream. Nothing is stored
    unless the whole output validated, so a failure or a disconnect part-way never
    leaves a half-written proposal. The agent runs in its own task so that closing
    the stream (a disconnect) cancels it cleanly.

    Args:
        db: The knowledge-base engine.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.
        text: The user's message.
        conversation: The conversation the message was stored in.
        evidence: The stored message's evidence id.

    Yields:
        One JSON object per line.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    task = asyncio.create_task(
        _produce(queue, db, embedder, model_factory, text, conversation, evidence)
    )
    try:
        while (line := await queue.get()) is not None:
            yield line
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@router.post("/chat/messages/stream")
async def post_message_stream(
    db: Engine, body: ChatRequest, embedder: Embedder, model_factory: Factory
) -> StreamingResponse:
    """Like `post_message`, but streams the reply as NDJSON (FR-13).

    Events, one JSON object per line: `delta` (growth of the reply), `proposal`
    (the stored proposal, rejected items and ids), `done`; or `error`, after which
    the stream ends. Streaming does not retry an invalid final output: it is an
    `error` event (ADR-0014). Size and conversation checks happen before the stream
    starts, so they are ordinary 422/404 responses.

    Args:
        db: The knowledge-base engine.
        body: The message.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.

    Returns:
        An `application/x-ndjson` stream.
    """
    conversation, evidence = await run_in_threadpool(_store_message, db, body)
    return StreamingResponse(
        stream_events(db, embedder, model_factory, body.text, conversation, evidence),
        media_type="application/x-ndjson",
    )
