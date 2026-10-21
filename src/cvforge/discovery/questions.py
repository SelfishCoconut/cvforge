"""Targeted questions derived from a posting's stored matches (FR-30, FR-32).

Deterministic and model-free: a question is built from the requirement's own words and the
rationale of its stored verdict, so it can only be about something the posting asked for.
An `undocumented` requirement is plausibly true but unrecorded, so it earns a *discovery*
question. A `gap` is not asked about in discovery (it feeds the learning planner); an
interview may still check one, because a recorded gap can be out of date.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from cvforge.jobs.store import get_posting
from cvforge.kb.vocab import MatchVerdict
from cvforge.match.store import list_matches


@dataclass(frozen=True)
class Question:
    """One question about one requirement.

    Attributes:
        requirement_id: The requirement it is about.
        requirement_text: What the posting asks.
        verdict: `undocumented` or `gap`.
        text: The question, in the user's language of the posting's requirement.
    """

    requirement_id: int
    requirement_text: str
    verdict: MatchVerdict
    text: str


def _discovery_text(requirement: str, rationale: str) -> str:
    return (
        f"The posting asks for “{requirement}”. {rationale.capitalize()}. "
        "Have you done this? If so, where, what exactly did you do, and what came of it?"
    )


def _gap_text(requirement: str, rationale: str) -> str:
    return (
        f"The posting asks for “{requirement}”, and your profile says: "
        f"{rationale}. Is that still accurate? If you have any experience with it, describe it."
    )


def questions_for(engine: Engine, posting_id: int, *, include_gaps: bool = False) -> list[Question]:
    """The questions a posting's stored matches call for.

    Args:
        engine: The knowledge-base engine.
        posting_id: A matched `job_posting` id.
        include_gaps: Also ask about `gap` requirements (interview mode). Discovery leaves
            them to the learning planner.

    Returns:
        One question per `undocumented` (and optionally `gap`) requirement, in requirement
        order; empty if the posting is unknown or not matched.
    """
    posting = get_posting(engine, posting_id)
    if posting is None:
        return []
    texts = {r.id: r.text for r in posting.requirements}
    questions: list[Question] = []
    for match in list_matches(engine, posting_id):
        requirement = texts.get(match.requirement_id)
        if requirement is None:
            continue
        if match.verdict is MatchVerdict.UNDOCUMENTED:
            text = _discovery_text(requirement, match.rationale)
        elif match.verdict is MatchVerdict.GAP and include_gaps:
            text = _gap_text(requirement, match.rationale)
        else:
            continue
        questions.append(Question(match.requirement_id, requirement, match.verdict, text))
    return questions
