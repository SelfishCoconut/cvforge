"""Closed vocabularies of the knowledge base (design spec §4).

Every value set here is closed. Adding a member is a design decision: `Rel` and
`EntityKind` changes need an ADR (kb-schema skill). The same sets are enforced
twice — by Pydantic at the model boundary and by CHECK constraints in the
schema — so a value that slips past one still cannot reach a row.
"""

from enum import StrEnum


class EntityKind(StrEnum):
    """The eight entity kinds (spec §4.1)."""

    SKILL = "skill"
    PROJECT = "project"
    ORGANIZATION = "organization"
    ROLE = "role"
    EDUCATION = "education"
    CREDENTIAL = "credential"
    ACHIEVEMENT = "achievement"
    RESPONSIBILITY = "responsibility"


class Rel(StrEnum):
    """The closed relationship vocabulary (spec §4.2). Never invent a value."""

    USED_IN = "used_in"
    AT_ORGANIZATION = "at_organization"
    PRODUCED = "produced"
    INVOLVED = "involved"
    DEMONSTRATES = "demonstrates"
    TAUGHT_BY = "taught_by"
    PART_OF = "part_of"
    RELATED_TO = "related_to"


class KnowledgeState(StrEnum):
    """Knowledge state of an entity (spec §4.4). Not a match verdict."""

    CONFIRMED = "confirmed"
    LEARNING = "learning"
    GAP = "gap"
    ARCHIVED = "archived"


class SourceKind(StrEnum):
    """Where a piece of evidence was captured from (spec §4.3)."""

    CONVERSATION = "conversation"
    DOCUMENT = "document"
    WEB = "web"
    MANUAL = "manual"


class TargetKind(StrEnum):
    """What an assertion or a classification points at."""

    ENTITY = "entity"
    EDGE = "edge"


class Origin(StrEnum):
    """Which intake produced a proposal (spec §4.5)."""

    CHAT = "chat"
    DOCUMENT = "document"
    INTERVIEW = "interview"
    WEB = "web"


class OpType(StrEnum):
    """Typed operations a proposal may contain (spec §4.5)."""

    CREATE_ENTITY = "create_entity"
    UPDATE_FIELD = "update_field"
    ADD_EDGE = "add_edge"
    ATTACH_EVIDENCE = "attach_evidence"
    MERGE_DUPLICATE = "merge_duplicate"
    SET_STATE = "set_state"


class Classification(StrEnum):
    """How an operation relates to what is already stored (ADR-0009)."""

    NEW = "new"
    KNOWN = "known"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class OpStatus(StrEnum):
    """Review status of a single operation (spec §4.5)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    APPLIED = "applied"


class ProposalStatus(StrEnum):
    """Lifecycle of a proposal: open for review, then committed exactly once."""

    OPEN = "open"
    COMMITTED = "committed"


# Kind-specific closed sets (spec §4.1 comments).
SKILL_CATEGORIES = ("language", "framework", "tool", "platform", "method", "soft")
ORG_TYPES = ("employer", "client", "institution")
CREDENTIAL_TYPES = ("certification", "course", "bootcamp")


def values(enum: type[StrEnum]) -> tuple[str, ...]:
    """Return the members of a vocabulary as plain strings, in declaration order.

    Args:
        enum: One of the vocabularies above.

    Returns:
        The string values, for CHECK constraints and error messages.
    """
    return tuple(member.value for member in enum)
