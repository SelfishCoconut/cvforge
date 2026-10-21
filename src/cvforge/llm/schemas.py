"""What an ingest agent may say: facts and edges, before they become operations.

These are the model-facing shapes. They carry no evidence and no classification;
`llm.convert` turns them into typed payloads and the database classifies them.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from cvforge.kb.vocab import EntityKind, Rel, WorkModel


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


class DocumentFact(ExtractedFact):
    """A fact read from a document, with the passage that states it.

    The page is not asked for: the server knows which page each chunk came from.
    """

    excerpt: str = Field(description="The passage that states this fact, copied verbatim.")


class DocumentEdge(ExtractedEdge):
    """A relationship read from a document, with the passage that states it."""

    excerpt: str = Field(description="The passage that states this, copied verbatim.")


class DocumentResult(BaseModel):
    """What the document agent extracted from one chunk of a document."""

    facts: list[DocumentFact] = Field(default_factory=list)
    edges: list[DocumentEdge] = Field(default_factory=list)


class JobAnalysis(BaseModel):
    """What a job posting states, field by field (FR-18).

    Every field is either read from the posting or explicitly empty (`None`, or an
    empty list): a value the posting does not state is never guessed. Blank strings
    count as empty, and list entries are stripped and de-duplicated.

    Attributes:
        title: The job title.
        company: The hiring organization.
        seniority: The seniority level as stated (e.g. "senior", "junior").
        required_skills: Skills the posting requires.
        preferred_skills: Skills the posting lists as nice to have.
        responsibilities: What the role will do.
        technologies: Named tools, languages, frameworks and platforms.
        experience_requirements: Experience asked for (years, domains, degrees).
        keywords: Terms an application should echo, as the posting words them.
        location: Where the job is based.
        working_model: Remote, hybrid or on-site, if stated.
        other_requirements: Anything else required (languages, clearance, travel).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    company: str | None = None
    seniority: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    working_model: WorkModel | None = None
    other_requirements: list[str] = Field(default_factory=list)

    @field_validator("title", "company", "seniority", "location")
    @classmethod
    def _blank_is_empty(cls, value: str | None) -> str | None:
        stripped = value.strip() if value else ""
        return stripped or None

    @field_validator(
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "technologies",
        "experience_requirements",
        "keywords",
        "other_requirements",
    )
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned = (value.strip() for value in values)
        return list(dict.fromkeys(value for value in cleaned if value))
