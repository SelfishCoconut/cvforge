"""The interview agent: reads an interview transcript and proposes facts (FR-32).

Same read-only knowledge tools as the ingest agent, a different prompt: the questions come from
an untrusted job posting, so only the user's answers may state facts.
"""

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from cvforge.llm import tools
from cvforge.llm.schemas import IngestResult
from cvforge.llm.tools import KbDeps

_PROMPT = (Path(__file__).parent.parent / "prompts" / "interview.md").read_text(encoding="utf-8")


def build_interview_agent(model: Model) -> Agent[KbDeps, IngestResult]:
    """Build the interview agent over `model`, with read-only knowledge-base tools.

    Args:
        model: The model to run against.

    Returns:
        An agent whose output is an `IngestResult`.
    """
    return Agent(
        model,
        deps_type=KbDeps,
        output_type=IngestResult,
        instructions=_PROMPT,
        tools=list(tools.TOOLS),
    )
