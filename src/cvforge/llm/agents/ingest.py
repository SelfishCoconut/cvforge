"""The ingest agent: reads one chat message and proposes facts (FR-06, FR-07)."""

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from cvforge.llm import tools
from cvforge.llm.schemas import IngestResult
from cvforge.llm.tools import KbDeps

_PROMPT = (Path(__file__).parent.parent / "prompts" / "ingest.md").read_text(encoding="utf-8")


def build_ingest_agent(model: Model) -> Agent[KbDeps, IngestResult]:
    """Build the ingest agent over `model`, with read-only knowledge-base tools.

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
