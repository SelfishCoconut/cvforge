"""The entities and evidence behind a verdict, and the gap report (FR-22, FR-23).

Everything here is read-only: it joins stored matches to the knowledge base through
`kb.queries`, so what a verdict cites can always be traced to a source span (invariant 3).
"""

from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa

from cvforge.jobs.store import StoredPosting
from cvforge.kb import queries
from cvforge.kb.vocab import EntityKind, KnowledgeState, MatchVerdict, TargetKind
from cvforge.match.store import StoredMatch, list_matches
from cvforge.match.verdicts import USED_RELS

MAX_EVIDENCE: Final = 5
_GAPS = frozenset({MatchVerdict.UNDOCUMENTED, MatchVerdict.GAP})


@dataclass(frozen=True)
class EvidenceSpan:
    """One resolvable span of source text.

    Attributes:
        source_id: The source it comes from.
        source_kind: `conversation`, `document`, `web` or `manual`.
        source_label: The source's label.
        locator: Where in the source.
        excerpt: The literal text.
    """

    source_id: int
    source_kind: str
    source_label: str
    locator: str
    excerpt: str


@dataclass(frozen=True)
class SupportingEntity:
    """An entity a verdict rests on, with the evidence for it.

    Attributes:
        entity_id: The entity (fetchable with `queries.get_entity`).
        name: Its name.
        kind: Its kind.
        state: Its current knowledge state.
        archived: True if it has been archived since the match: it no longer backs a claim.
        evidence: Spans stating the entity or one of its recorded uses.
    """

    entity_id: int
    name: str
    kind: EntityKind
    state: KnowledgeState
    archived: bool
    evidence: tuple[EvidenceSpan, ...]


@dataclass(frozen=True)
class DetailedMatch:
    """A stored verdict with its supporting entities resolved.

    Attributes:
        match: The stored verdict.
        support: The backing entities; empty for `undocumented` and `gap`.
    """

    match: StoredMatch
    support: tuple[SupportingEntity, ...]


@dataclass(frozen=True)
class GapEntry:
    """A requirement the knowledge base does not back.

    Attributes:
        requirement_id: The requirement, for linking back to the posting.
        verdict: `undocumented` or `gap`.
        score: Closeness of the nearest plausible entity, if any.
        rationale: Why.
    """

    requirement_id: int
    verdict: MatchVerdict
    score: float | None
    rationale: str


def _spans(conn: sa.Connection, kind: TargetKind, target_id: int) -> list[EvidenceSpan]:
    return [
        EvidenceSpan(p.source_id, p.source_kind, p.source_label, p.locator, p.excerpt)
        for p in queries.provenance(conn, kind, target_id)
    ]


def _supporting(conn: sa.Connection, entity_id: int) -> SupportingEntity | None:
    record = queries.get_entity(conn, entity_id)
    if record is None:
        return None
    spans = _spans(conn, TargetKind.ENTITY, entity_id)
    for edge in queries.neighbours(conn, entity_id):
        if edge.rel in USED_RELS:
            spans.extend(_spans(conn, TargetKind.EDGE, edge.id))
    unique = list(dict.fromkeys(spans))[:MAX_EVIDENCE]
    return SupportingEntity(
        record.id,
        record.name,
        record.kind,
        record.state,
        record.state is KnowledgeState.ARCHIVED,
        tuple(unique),
    )


def detailed_matches(engine: sa.Engine, matches: list[StoredMatch]) -> list[DetailedMatch]:
    """Resolve each match's supporting entities and their evidence.

    Args:
        engine: The knowledge-base engine.
        matches: Stored matches, from `list_matches`.

    Returns:
        One entry per match, same order. An entity that no longer exists is dropped from
        `support`; an archived one is kept and flagged.
    """
    with engine.connect() as conn:
        return [
            DetailedMatch(
                m,
                tuple(s for e in m.support if (s := _supporting(conn, e)) is not None),
            )
            for m in matches
        ]


def gap_report(engine: sa.Engine, posting: StoredPosting) -> list[GapEntry]:
    """List a posting's `undocumented` and `gap` requirements.

    Args:
        engine: The knowledge-base engine.
        posting: The posting.

    Returns:
        One entry per such requirement in requirement order; empty if everything is backed
        (or the posting has not been matched).
    """
    return [
        GapEntry(m.requirement_id, m.verdict, m.score, m.rationale)
        for m in list_matches(engine, posting.id)
        if m.verdict in _GAPS
    ]
