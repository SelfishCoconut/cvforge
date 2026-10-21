"""Discovery questions and interviews: answers become reviewable proposals (FR-30, FR-32).

Nothing here writes knowledge. An answer is stored as provenance (a conversation source), read
by the same tool-limited agents as chat, and recorded as a pending proposal that Álvaro
reviews and commits (invariant 4). Declining writes nothing at all.
"""

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from cvforge.api.chat import (
    ChatRequest,
    ChatResponse,
    Embedder,
    Factory,
    failure_message,
    finish_proposal,
    proposal_view,
    store_message,
)
from cvforge.api.errors import engine
from cvforge.discovery.questions import Question, questions_for
from cvforge.jobs.store import get_posting
from cvforge.kb import apply
from cvforge.kb.vocab import MatchVerdict, Origin
from cvforge.llm.agents.ingest import build_ingest_agent
from cvforge.llm.agents.interview import build_interview_agent
from cvforge.llm.fence import fence
from cvforge.llm.tools import KbDeps

router = APIRouter(tags=["discovery"])
Engine = Annotated[sa.Engine, Depends(engine)]


class QuestionView(BaseModel):
    """A question about one requirement.

    Attributes:
        requirement_id: The requirement it is about.
        requirement_text: What the posting asks.
        verdict: `undocumented` or `gap`.
        text: The question.
    """

    requirement_id: int
    requirement_text: str
    verdict: MatchVerdict
    text: str


class AnswerRequest(BaseModel):
    """An answer to a discovery question.

    Attributes:
        answer: What the user says, in their own words.
        conversation_id: Continue an existing conversation source, if any.
    """

    answer: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = None


class Turn(BaseModel):
    """One answered interview question.

    Attributes:
        requirement_id: The requirement the question was about.
        answer: What the user says; blank means they had nothing to add.
    """

    requirement_id: int
    answer: str = Field(max_length=8000)


class InterviewRequest(BaseModel):
    """An interview transcript.

    Attributes:
        turns: The answered questions, in the order they were asked.
    """

    turns: list[Turn] = Field(max_length=200)


def _view(question: Question) -> QuestionView:
    return QuestionView(
        requirement_id=question.requirement_id,
        requirement_text=question.requirement_text,
        verdict=question.verdict,
        text=question.text,
    )


def _require_posting(db: sa.Engine, posting_id: int) -> None:
    if get_posting(db, posting_id) is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")


@router.get("/jobs/{posting_id}/discovery")
def read_discovery(posting_id: int, db: Engine) -> list[QuestionView]:
    """List the discovery questions for a matched posting: one per `undocumented` requirement.

    A `gap` requirement is never asked about here; it feeds the learning planner.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The questions.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    _require_posting(db, posting_id)
    return [_view(q) for q in questions_for(db, posting_id)]


def _question(db: sa.Engine, posting_id: int, requirement_id: int) -> Question:
    _require_posting(db, posting_id)
    found = next(
        (q for q in questions_for(db, posting_id) if q.requirement_id == requirement_id), None
    )
    if found is None:
        raise HTTPException(409, f"requirement {requirement_id} raises no discovery question")
    return found


@router.post("/jobs/{posting_id}/discovery/{requirement_id}/answer")
def answer_question(
    posting_id: int,
    requirement_id: int,
    body: AnswerRequest,
    db: Engine,
    embedder: Embedder,
    model_factory: Factory,
) -> ChatResponse:
    """Answer a discovery question; the answer becomes a pending proposal, never a write.

    Args:
        posting_id: A posting id.
        requirement_id: The `undocumented` requirement the question was about.
        body: The answer.
        db: The knowledge-base engine.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.

    Returns:
        The agent's acknowledgement and the pending proposal (empty if nothing was stated).

    Raises:
        HTTPException: 409 if the requirement raises no discovery question (a `gap` or a
            backed requirement); 422 for a blank answer; 502 if the model fails.
    """
    question = _question(db, posting_id, requirement_id)
    if not body.answer.strip():
        raise HTTPException(422, "an empty answer states nothing; decline instead")
    conversation, evidence = store_message(
        db, ChatRequest(text=body.answer, conversation_id=body.conversation_id)
    )
    prompt = f"{fence('question', question.text)}\n\nThe user answered:\n{body.answer}"
    try:
        result = (
            build_ingest_agent(model_factory(db)).run_sync(prompt, deps=KbDeps(db, embedder)).output
        )
    except Exception as exc:
        raise HTTPException(502, failure_message(exc)) from exc
    return finish_proposal(db, embedder, conversation, evidence, result)


@router.post("/jobs/{posting_id}/discovery/{requirement_id}/decline", status_code=204)
def decline_question(posting_id: int, requirement_id: int, db: Engine) -> Response:
    """Decline a discovery question. Nothing is recorded: no entity, no source, no proposal.

    Args:
        posting_id: A posting id.
        requirement_id: The requirement the question was about.
        db: The knowledge-base engine.

    Returns:
        An empty 204.

    Raises:
        HTTPException: 409 if the requirement raises no discovery question.
    """
    _question(db, posting_id, requirement_id)
    return Response(status_code=204)


@router.get("/jobs/{posting_id}/interview")
def read_interview(posting_id: int, db: Engine) -> list[QuestionView]:
    """List the interview questions: one per `undocumented` or `gap` requirement.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The questions, derived from the posting's stored matches.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    _require_posting(db, posting_id)
    return [_view(q) for q in questions_for(db, posting_id, include_gaps=True)]


@router.post("/jobs/{posting_id}/interview")
def submit_interview(
    posting_id: int,
    body: InterviewRequest,
    db: Engine,
    embedder: Embedder,
    model_factory: Factory,
) -> ChatResponse:
    """Turn an interview transcript into one pending proposal (origin `interview`).

    Only the user's answers are read as facts. Blank answers are dropped; a transcript with no
    substantive answer records nothing and calls no model.

    Args:
        posting_id: A posting id.
        body: The answered questions.
        db: The knowledge-base engine.
        embedder: Used for similarity, if configured.
        model_factory: Builds the model for this request.

    Returns:
        The acknowledgement and the pending proposal.

    Raises:
        HTTPException: 422 for an answer to a requirement that was not asked about; 502 if the
            model fails.
    """
    _require_posting(db, posting_id)
    asked = {q.requirement_id: q for q in questions_for(db, posting_id, include_gaps=True)}
    unknown = [t.requirement_id for t in body.turns if t.requirement_id not in asked]
    if unknown:
        raise HTTPException(422, f"requirements {unknown} were not asked about")
    answered = [(asked[t.requirement_id], t.answer.strip()) for t in body.turns if t.answer.strip()]
    if not answered:
        return ChatResponse(
            conversation_id=0,
            message_id=0,
            reply="Nothing was said that adds to your profile.",
            proposal=proposal_view(db, None),
            rejected=[],
            similarity_available=embedder is not None,
        )
    transcript = "\n\n".join(f"Q: {q.text}\nA: {answer}" for q, answer in answered)
    conversation, evidence = store_message(
        db,
        ChatRequest(text="\n\n".join(answer for _, answer in answered)),
        label=f"interview for posting {posting_id}",
    )
    try:
        result = (
            build_interview_agent(model_factory(db))
            .run_sync(fence("interview", transcript), deps=KbDeps(db, embedder))
            .output
        )
    except Exception as exc:
        raise HTTPException(502, failure_message(exc)) from exc
    return finish_proposal(db, embedder, conversation, evidence, result, origin=Origin.INTERVIEW)
