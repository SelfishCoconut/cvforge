"""What an ingest agent may say: facts and edges, before they become operations.

These are the model-facing shapes. They carry no evidence and no classification;
`llm.convert` turns them into typed payloads and the database classifies them.
"""

from datetime import date

from pydantic import BaseModel, Field, JsonValue

from cvforge.kb.vocab import EntityKind, Rel


class ExtractedFact(BaseModel):
    """One entity the user's message states."""

    local_id: str = Field(description="A label unique within this result, used by edges.")
    kind: EntityKind
    name: str
    summary: str | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class ExtractedEdge(BaseModel):
    """A relationship between two facts, or between a fact and an existing entity."""

    src: str | int = Field(description="A fact's local_id, or an existing entity id.")
    rel: Rel
    dst: str | int = Field(description="A fact's local_id, or an existing entity id.")
    started_at: date | None = None
    ended_at: date | None = None
    note: str | None = None


class IngestResult(BaseModel):
    """The agent's output: a reply for the user and what it extracted."""

    reply: str
    facts: list[ExtractedFact] = Field(default_factory=list)
    edges: list[ExtractedEdge] = Field(default_factory=list)
