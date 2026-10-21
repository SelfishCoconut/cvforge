"""The document agent: reads one chunk of an uploaded document and proposes facts (FR-15)."""

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model

from cvforge.llm import tools
from cvforge.llm.schemas import DocumentResult
from cvforge.llm.tools import KbDeps

_PROMPT = (Path(__file__).parent.parent / "prompts" / "document.md").read_text(encoding="utf-8")


def build_document_agent(model: Model) -> Agent[KbDeps, DocumentResult]:
    """Build the document agent over `model`, with read-only knowledge-base tools.

    Args:
        model: The model to run against.

    Returns:
        An agent whose output is a `DocumentResult`.
    """
    return Agent(
        model,
        deps_type=KbDeps,
        output_type=DocumentResult,
        instructions=_PROMPT,
        tools=list(tools.TOOLS),
    )
