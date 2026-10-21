"""Persist and read the verdicts for a posting's requirements (FR-21, FR-22).

Registered writer (ADR-0011, ADR-0023): may write `match` and `match_support`, nothing
else. A match is derived from knowledge, not knowledge, so it carries no assertion. A new
run for a posting replaces that posting's matches in one transaction, so results are
never a mix of two runs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa

from cvforge.kb import schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import MatchVerdict
from cvforge.match.verdicts import Outcome


@dataclass(frozen=True)
class StoredMatch:
    """One stored verdict.

    Attributes:
        id: The `match` row id.
        requirement_id: The requirement it judges.
        verdict: The verdict.
        score: Closeness of the best backing or plausible entity, if any.
        rationale: Why.
        support: Backing entity ids, empty for undocumented/gap.
        computed_at: When the run happened.
    """

    id: int
    requirement_id: int
    verdict: MatchVerdict
    score: float | None
    rationale: str
    support: tuple[int, ...]
    computed_at: datetime


def replace_matches(
    engine: sa.Engine, posting_id: int, outcomes: Sequence[tuple[int, Outcome]]
) -> None:
    """Replace a posting's matches with `outcomes`.

    Args:
        engine: The knowledge-base engine.
        posting_id: The `job_posting` id.
        outcomes: (requirement id, outcome) pairs from `match_posting`.
    """
    now = utc_now()
    with write_transaction(engine) as conn:
        conn.execute(sa.delete(schema.match).where(schema.match.c.job_posting_id == posting_id))
        for requirement_id, outcome in outcomes:
            match_id = int(
                conn.execute(
                    sa.insert(schema.match)
                    .values(
                        job_posting_id=posting_id,
                        requirement_id=requirement_id,
                        verdict=outcome.verdict.value,
                        score=outcome.score,
                        rationale=outcome.rationale,
                        computed_at=now,
                    )
                    .returning(schema.match.c.id)
                ).scalar_one()
            )
            if outcome.support:
                conn.execute(
                    sa.insert(schema.match_support),
                    [{"match_id": match_id, "entity_id": e} for e in outcome.support],
                )


def list_matches(engine: sa.Engine, posting_id: int) -> list[StoredMatch]:
    """Read a posting's stored matches in requirement order.

    Args:
        engine: The knowledge-base engine.
        posting_id: The `job_posting` id.

    Returns:
        The matches; empty if the posting has not been matched.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(schema.match)
            .where(schema.match.c.job_posting_id == posting_id)
            .order_by(schema.match.c.requirement_id)
        ).all()
        support: dict[int, list[int]] = {}
        for row in conn.execute(
            sa.select(schema.match_support)
            .where(schema.match_support.c.match_id.in_([r.id for r in rows]))
            .order_by(schema.match_support.c.entity_id)
        ):
            support.setdefault(row.match_id, []).append(row.entity_id)
    return [
        StoredMatch(
            r.id,
            r.requirement_id,
            MatchVerdict(r.verdict),
            r.score,
            r.rationale,
            tuple(support.get(r.id, [])),
            r.computed_at,
        )
        for r in rows
    ]
