"""The adjacency judge: does what is recorded imply a job requirement? (FR-21).

Tool-free, like the job agent (ADR-0020): the requirement comes from an untrusted posting.
The matching engine validates every id this returns against the candidates it offered, so
the model can lower a verdict's certainty but never invent support.
"""

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model

from cvforge.llm.fence import fence
from cvforge.match.verdicts import Candidate, Judgment

_PROMPT = (Path(__file__).parent.parent / "prompts" / "adjacency.md").read_text(encoding="utf-8")


class JudgeOutput(BaseModel):
    """What the model answers.

    Attributes:
        entity_ids: Candidates that imply the requirement; empty if none do.
        rationale: The inference in one sentence.
    """

    entity_ids: list[int] = Field(default_factory=list)
    rationale: str = ""


def build_adjacency_agent(model: Model) -> Agent[None, JudgeOutput]:
    """Build the judge agent over `model`.

    Args:
        model: The model to run against.

    Returns:
        A tool-free agent whose output is a `JudgeOutput`.
    """
    return Agent(model, output_type=JudgeOutput, instructions=_PROMPT)


class ModelJudge:
    """An `AdjacencyJudge` backed by a model."""

    def __init__(self, model: Model) -> None:
        """Create the judge.

        Args:
            model: The model to run against.
        """
        self._agent = build_adjacency_agent(model)

    def judge(self, requirement: str, candidates: Sequence[Candidate]) -> Judgment:
        """Ask the model which candidates imply `requirement`.

        Args:
            requirement: The requirement text (untrusted).
            candidates: Recorded, used entities it may be judged against.

        Returns:
            The judgment; no ids if the model's output was invalid.
        """
        listing = "\n".join(
            f"- id {c.entity_id}: {c.name} ({c.kind.value})"
            + (f" - {c.summary}" if c.summary else "")
            for c in candidates
        )
        prompt = f"{fence('requirement', requirement)}\n\nCandidates:\n{listing}"
        try:
            output = self._agent.run_sync(prompt).output
        except UnexpectedModelBehavior:
            return Judgment((), "")
        return Judgment(tuple(output.entity_ids), output.rationale)
