"""The plan agent: drafts a learning plan for one gap requirement (FR-33).

Tool-free and read-only: the requirement comes from an untrusted posting, and a plan is advice,
not knowledge, so nothing it says is written to the knowledge base.
"""

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from cvforge.kb.vocab import StepKind
from cvforge.llm.fence import fence

_PROMPT = (Path(__file__).parent.parent / "prompts" / "plan.md").read_text(encoding="utf-8")
MAX_STEPS = 8


class PlanStep(BaseModel):
    """One step of a learning plan.

    Attributes:
        title: What to do, briefly.
        kind: `study`, `reading`, `exercise` or `project`.
        resource: A well-known resource to use, if any.
        done_when: An observable sign the step is finished.
    """

    title: str = Field(min_length=1)
    kind: StepKind
    resource: str | None = None
    done_when: str = Field(min_length=1)


class PlanDraft(BaseModel):
    """What the agent answers.

    Attributes:
        summary: One sentence on the route.
        steps: The ordered steps.
    """

    summary: str = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1, max_length=MAX_STEPS)


def build_plan_agent(model: Model) -> Agent[None, PlanDraft]:
    """Build the plan agent over `model`.

    Args:
        model: The model to run against.

    Returns:
        A tool-free agent whose output is a `PlanDraft`.
    """
    return Agent(model, output_type=PlanDraft, instructions=_PROMPT)


def plan_prompt(requirement: str, skills: Sequence[str]) -> str:
    """The prompt for one plan: the requirement and the user's skills, each fenced as data.

    Args:
        requirement: The gap requirement's text.
        skills: Names of the user's confirmed skills.

    Returns:
        The prompt text.
    """
    return f"{fence('requirement', requirement)}\n\n{fence('skills', ', '.join(skills) or 'none')}"
