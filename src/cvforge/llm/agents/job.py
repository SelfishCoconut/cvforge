"""The job agent: reads one fetched posting and reports what it states (FR-18).

It has no tools at all. The posting is untrusted (NFR-07), and analysing it needs
nothing from the knowledge base (matching is a later step), so there is nothing a
hostile posting could talk the model into calling.
"""

import re
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model

from cvforge.llm.schemas import JobAnalysis

_PROMPT = (Path(__file__).parent.parent / "prompts" / "job.md").read_text(encoding="utf-8")
_CLOSE = "</posting>"
_CLOSE_PATTERN = re.compile(r"<\s*/\s*posting\s*>", re.IGNORECASE)


class AnalysisError(Exception):
    """The model did not return a valid `JobAnalysis`."""


def build_job_agent(model: Model) -> Agent[None, JobAnalysis]:
    """Build the job agent over `model`.

    Args:
        model: The model to run against.

    Returns:
        A tool-free agent whose output is a `JobAnalysis`.
    """
    return Agent(model, output_type=JobAnalysis, instructions=_PROMPT)


def _prompt(posting_text: str) -> str:
    """Fence the posting so it reads as data; a closing tag inside it cannot end the fence."""
    safe = posting_text
    while (stripped := _CLOSE_PATTERN.sub("", safe)) != safe:  # a removal can rebuild a closer
        safe = stripped
    return f"<posting>\n{safe}\n{_CLOSE}"


def analyze_posting(model: Model, posting_text: str) -> JobAnalysis:
    """Analyse a posting's text.

    Args:
        model: The model to run against.
        posting_text: The text of the posting, as fetched.

    Returns:
        The structured analysis. Nothing is stored: persisting it is FR-20.

    Raises:
        AnalysisError: If the model's output never validated against `JobAnalysis`.
    """
    try:
        return build_job_agent(model).run_sync(_prompt(posting_text)).output
    except UnexpectedModelBehavior as exc:
        raise AnalysisError(f"the model returned no valid job analysis: {exc}") from exc
