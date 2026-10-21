"""Decide how well the knowledge base backs a requirement (FR-21, spec §4.6).

The database decides, not the model (invariant 1). A requirement is `satisfied` when a
confirmed entity of that name has a recorded use; `evidenced` when a close, used entity
backs it (by similarity, or by an inference an optional judge states and the code
validates); `undocumented` when it is plausible for the recorded profile but nothing
states it; and `gap` otherwise. `undocumented` and `gap` never carry a supporting entity.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import sqlalchemy as sa

from cvforge.jobs.store import get_posting
from cvforge.kb import queries
from cvforge.kb.embeddings import EmbeddingError, EmbeddingProvider, find_similar
from cvforge.kb.vocab import EntityKind, KnowledgeState, MatchVerdict, Rel
from cvforge.llm.settings_store import load_settings

USED_RELS: Final = frozenset({Rel.USED_IN.value, Rel.DEMONSTRATES.value})
PLAUSIBLE_FLOOR: Final = 0.6
MAX_CANDIDATES: Final = 5


@dataclass(frozen=True)
class Candidate:
    """A recorded, used entity offered to the judge as possible support.

    Attributes:
        entity_id: The entity.
        name: Its name.
        kind: Its kind.
        summary: Its summary, if any.
        score: Cosine similarity to the requirement.
    """

    entity_id: int
    name: str
    kind: EntityKind
    summary: str | None
    score: float


@dataclass(frozen=True)
class Judgment:
    """What a judge concluded about a requirement.

    Attributes:
        entity_ids: The candidates that imply the requirement; empty if none do.
        rationale: The inference, in words.
    """

    entity_ids: tuple[int, ...]
    rationale: str


class AdjacencyJudge(Protocol):
    """Decides whether recorded entities imply a requirement (a framework implies its language)."""

    def judge(self, requirement: str, candidates: Sequence[Candidate]) -> Judgment:
        """Say which candidates, if any, imply `requirement`.

        Args:
            requirement: The requirement text (untrusted).
            candidates: The recorded, used entities it may be judged against.

        Returns:
            The judgment.
        """
        ...


@dataclass(frozen=True)
class Outcome:
    """The verdict for one requirement.

    Attributes:
        verdict: One of the four verdicts.
        score: How close the best backing or plausible entity is, if any.
        rationale: Why, in words.
        support: Entity ids behind a `satisfied` or `evidenced` verdict; empty otherwise.
    """

    verdict: MatchVerdict
    score: float | None
    rationale: str
    support: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """Hold the invariant: only `satisfied` and `evidenced` rest on entities, and both do."""
        backed = self.verdict in (MatchVerdict.SATISFIED, MatchVerdict.EVIDENCED)
        if backed != bool(self.support):
            raise ValueError(
                f"a {self.verdict.value} verdict must{'' if backed else ' not'} cite support"
            )


def _uses(conn: sa.Connection, entity_id: int) -> int:
    return sum(1 for edge in queries.neighbours(conn, entity_id) if edge.rel in USED_RELS)


def _recorded(conn: sa.Connection, text: str) -> list[queries.EntityRecord]:
    """Entities, of any kind, whose normalised name is the requirement's, archived excluded."""
    ids = [i for kind in EntityKind for i in queries.find_by_name(conn, kind, text)]
    records = (queries.get_entity(conn, i) for i in sorted(ids))
    return [r for r in records if r is not None and r.state is not KnowledgeState.ARCHIVED]


def _from_recorded(conn: sa.Connection, recorded: list[queries.EntityRecord]) -> Outcome | None:
    """The verdict an exact name match decides, or None if there is no such entity."""
    if not recorded:
        return None
    used = [(r, _uses(conn, r.id)) for r in recorded if r.state is KnowledgeState.CONFIRMED]
    backed = [(r, n) for r, n in used if n > 0]
    if backed:
        names = ", ".join(f"'{r.name}'" for r, _ in backed)
        uses = sum(n for _, n in backed)
        return Outcome(
            MatchVerdict.SATISFIED,
            1.0,
            f"recorded as {names} (confirmed) with {uses} recorded use(s)",
            tuple(r.id for r, _ in backed),
        )
    first = recorded[0]
    if first.state is KnowledgeState.GAP:
        return Outcome(MatchVerdict.GAP, None, f"'{first.name}' is recorded as a gap")
    if first.state is KnowledgeState.LEARNING:
        return Outcome(MatchVerdict.GAP, None, f"'{first.name}' is still being learned")
    return Outcome(
        MatchVerdict.UNDOCUMENTED,
        1.0,
        f"'{first.name}' is recorded but no use of it is recorded",
    )


def _usable(
    engine: sa.Engine, provider: EmbeddingProvider, text: str, threshold: float
) -> tuple[list[Candidate], float | None, str | None]:
    """Close entities that are confirmed and used, the best plausible score, its name."""
    hits = find_similar(
        engine, provider, text, threshold=min(PLAUSIBLE_FLOOR, threshold), limit=MAX_CANDIDATES
    )
    usable: list[Candidate] = []
    with engine.connect() as conn:
        for hit in hits:
            record = queries.get_entity(conn, hit.entity_id)
            if record and record.state is KnowledgeState.CONFIRMED and _uses(conn, record.id):
                usable.append(
                    Candidate(record.id, record.name, record.kind, record.summary, hit.score)
                )
    best = hits[0] if hits else None
    return usable, (best.score if best else None), (best.name if best else None)


def _judged(judge: AdjacencyJudge | None, text: str, usable: list[Candidate]) -> Outcome | None:
    """An `evidenced` outcome from the judge, only if its answer survives validation."""
    if judge is None or not usable:
        return None
    judgment = judge.judge(text, usable)
    by_id = {c.entity_id: c for c in usable}
    chosen = [by_id[i] for i in dict.fromkeys(judgment.entity_ids) if i in by_id]
    unknown = [i for i in judgment.entity_ids if i not in by_id]
    if not chosen or unknown or not judgment.rationale.strip():
        return None
    return Outcome(
        MatchVerdict.EVIDENCED,
        max(c.score for c in chosen),
        judgment.rationale.strip(),
        tuple(c.entity_id for c in chosen),
    )


def _from_similarity(
    engine: sa.Engine,
    provider: EmbeddingProvider,
    judge: AdjacencyJudge | None,
    text: str,
    threshold: float,
) -> Outcome | None:
    """The verdict similarity decides, or None if nothing is close."""
    usable, best, best_name = _usable(engine, provider, text, threshold)
    strong = [c for c in usable if c.score >= threshold]
    if strong:
        names = ", ".join(f"'{c.name}' ({c.score:.2f})" for c in strong)
        return Outcome(
            MatchVerdict.EVIDENCED,
            strong[0].score,
            f"not recorded under this name, but close to {names}, which is used",
            tuple(c.entity_id for c in strong),
        )
    if (judged := _judged(judge, text, usable)) is not None:
        return judged
    if best is not None:
        return Outcome(
            MatchVerdict.UNDOCUMENTED,
            best,
            f"plausible for the recorded profile (closest '{best_name}', {best:.2f}) "
            "but nothing recorded states it",
        )
    return None


def match_requirement(
    engine: sa.Engine,
    text: str,
    *,
    embedder: EmbeddingProvider | None = None,
    judge: AdjacencyJudge | None = None,
    threshold: float = 0.85,
) -> Outcome:
    """Decide the verdict for one requirement.

    Args:
        engine: The knowledge-base engine.
        text: The requirement text.
        embedder: Used for similarity; without one, only exact name matches count.
        judge: Optional inference for requirements close to, but not named by, the profile.
        threshold: Similarity at or above which a used entity backs the requirement.

    Returns:
        The verdict, its rationale and any supporting entity ids.
    """
    with engine.connect() as conn:
        decided = _from_recorded(conn, _recorded(conn, text))
    if decided is not None:
        return decided
    if embedder is not None:
        try:
            similar = _from_similarity(engine, embedder, judge, text, threshold)
        except EmbeddingError:
            return Outcome(MatchVerdict.GAP, None, "no recorded entity; similarity was unavailable")
        if similar is not None:
            return similar
    return Outcome(MatchVerdict.GAP, None, "no recorded entity and nothing plausibly close")


def match_posting(
    engine: sa.Engine,
    posting_id: int,
    *,
    embedder: EmbeddingProvider | None = None,
    judge: AdjacencyJudge | None = None,
) -> list[tuple[int, Outcome]] | None:
    """Decide a verdict for every requirement of a stored posting.

    Args:
        engine: The knowledge-base engine.
        posting_id: A `job_posting` id.
        embedder: Used for similarity, if available.
        judge: Optional inference step.

    Returns:
        (requirement id, outcome) per requirement, in stored order; None if there is no
        such posting.
    """
    posting = get_posting(engine, posting_id)
    if posting is None:
        return None
    threshold = load_settings(engine).similarity_threshold
    return [
        (
            requirement.id,
            match_requirement(
                engine, requirement.text, embedder=embedder, judge=judge, threshold=threshold
            ),
        )
        for requirement in posting.requirements
    ]
