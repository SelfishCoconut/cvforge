"""Agent registry. The read-only test iterates `AGENTS`, so no agent ships a write tool."""

from collections.abc import Callable
from typing import Any

from pydantic_ai import Agent

from cvforge.llm.agents.document import build_document_agent
from cvforge.llm.agents.ingest import build_ingest_agent
from cvforge.llm.agents.interview import build_interview_agent

AGENTS: dict[str, Callable[..., Agent[Any, Any]]] = {
    "ingest": build_ingest_agent,
    "document": build_document_agent,
    "interview": build_interview_agent,
}
