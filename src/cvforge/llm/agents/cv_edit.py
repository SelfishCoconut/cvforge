"""The CV edit agent: turns a chat instruction into edit operations (FR-31).

Tool-free, like the other agents that read text they do not control: the CV lines come from the
knowledge base. It proposes operations; `cv/edit.py` checks every one against the stored facts, so
the model can change phrasing and order but cannot add support the knowledge base does not have.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from cvforge.cv.store import StoredCv
from cvforge.llm.fence import fence

_PROMPT = (Path(__file__).parent.parent / "prompts" / "cv_edit.md").read_text(encoding="utf-8")


class EditOp(BaseModel):
    """One proposed operation.

    Attributes:
        kind: `reword`, `drop` or `emphasize`.
        claim_id: The numbered CV line (reword, drop).
        text: The new wording (reword).
        name: What to bring to the front (emphasize).
    """

    kind: Literal["reword", "drop", "emphasize"]
    claim_id: int | None = None
    text: str | None = None
    name: str | None = None


class EditPlan(BaseModel):
    """What the agent answers.

    Attributes:
        ops: The operations, in order.
        reply: A short plain-language account for the user.
    """

    ops: list[EditOp] = Field(default_factory=list)
    reply: str = ""


def build_cv_edit_agent(model: Model) -> Agent[None, EditPlan]:
    """Build the edit agent over `model`.

    Args:
        model: The model to run against.

    Returns:
        A tool-free agent whose output is an `EditPlan`.
    """
    return Agent(model, output_type=EditPlan, instructions=_PROMPT)


def edit_prompt(cv: StoredCv, instruction: str) -> str:
    """The prompt for one edit: the user's instruction, then the CV as fenced numbered lines.

    Args:
        cv: The CV being edited.
        instruction: What the user asked for.

    Returns:
        The prompt text.
    """
    lines = "\n".join(
        f"[{c.id}] {c.section} / {c.slot.value}: {' '.join(c.text.split())}" for c in cv.claims
    )
    return f"Instruction: {instruction}\n\n{fence('cv', lines)}"
