"""Persist a fetched, analysed job posting and its requirements (FR-20).

Registered writer (ADR-0011, ADR-0020): may write `job_posting` and `requirement`,
nothing else. A posting is not knowledge about Álvaro (no assertion, no evidence), so
it does not go through the knowledge writer. Its raw page is still traceable: every
persist records a `web` source through `kb.apply.record_source`, and
`job_posting.source_id` points at it.

Re-persisting a URL is an update, not a duplicate: postings are keyed by the
normalised URL (ADR-0020 D-O), the row keeps its id, and its requirements are replaced
by the new analysis.
"""

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy as sa

from cvforge.kb import apply, schema
from cvforge.kb.db import utc_now, write_transaction
from cvforge.kb.vocab import RequirementKind, SourceKind
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.fetch import FetchedPage

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class PersistedPosting:
    """What `persist_posting` stored.

    Attributes:
        id: The `job_posting` row id (unchanged when the URL was already stored).
        created: True if this was a new posting, False if an existing one was updated.
        source_id: The `web` source recording this fetch.
        requirement_count: How many `requirement` rows the posting now has.
    """

    id: int
    created: bool
    source_id: int
    requirement_count: int


def normalize_url(url: str) -> str:
    """The key under which a posting URL is deduplicated.

    The scheme and host are lower-cased, a default port and the fragment are dropped.
    The path and query are kept as they are: job boards identify postings by them.

    Args:
        url: A posting URL.

    Returns:
        The normalised URL.
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(parts.scheme):
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))


def decompose(analysis: JobAnalysis) -> list[tuple[RequirementKind, str]]:
    """Split an analysis into individual requirements, in a fixed order.

    Required skills, stated experience and other requirements are `required`; preferred
    skills are `preferred`; responsibilities are `responsibility`. A text repeated within
    a kind appears once.

    Args:
        analysis: The structured analysis of a posting.

    Returns:
        (kind, text) pairs.
    """
    groups = (
        (RequirementKind.REQUIRED, analysis.required_skills),
        (RequirementKind.REQUIRED, analysis.experience_requirements),
        (RequirementKind.REQUIRED, analysis.other_requirements),
        (RequirementKind.PREFERRED, analysis.preferred_skills),
        (RequirementKind.RESPONSIBILITY, analysis.responsibilities),
    )
    seen: set[tuple[RequirementKind, str]] = set()
    pairs: list[tuple[RequirementKind, str]] = []
    for kind, texts in groups:
        for text in texts:
            if (kind, text) not in seen:
                seen.add((kind, text))
                pairs.append((kind, text))
    return pairs


def persist_posting(
    engine: sa.Engine, page: FetchedPage, analysis: JobAnalysis, *, url: str | None = None
) -> PersistedPosting:
    """Store a posting and its requirements, or update the one already stored for its URL.

    Args:
        engine: The knowledge-base engine.
        page: The fetched page; its text is stored as the posting's raw text.
        analysis: The structured analysis of `page`.
        url: The URL to key the posting by; defaults to the one that was requested.

    Returns:
        The stored posting's id and counts.
    """
    key = normalize_url(url or page.url)
    source_id = apply.record_source(
        engine,
        SourceKind.WEB,
        page.title or key,
        uri=page.final_url,
        content_hash=hashlib.sha256(page.text.encode()).hexdigest(),
    )
    values: dict[str, Any] = {
        "source_id": source_id,
        "title": analysis.title,
        "seniority": analysis.seniority,
        "location": analysis.location,
        "work_model": analysis.working_model.value if analysis.working_model else None,
        "raw_text": page.text,
        "analysis_json": analysis.model_dump_json(),
        "fetched_at": utc_now(),
    }
    requirements = decompose(analysis)
    with write_transaction(engine) as conn:
        existing = conn.execute(
            sa.select(schema.job_posting.c.id).where(schema.job_posting.c.url == key)
        ).scalar()
        if existing is None:
            posting_id = _insert(conn, key, values)
        else:
            posting_id = existing
            conn.execute(
                sa.update(schema.job_posting)
                .where(schema.job_posting.c.id == posting_id)
                .values(**values)
            )
            conn.execute(
                sa.delete(schema.requirement).where(
                    schema.requirement.c.job_posting_id == posting_id
                )
            )
        if requirements:
            conn.execute(
                sa.insert(schema.requirement),
                [
                    {"job_posting_id": posting_id, "kind": kind.value, "text": text}
                    for kind, text in requirements
                ],
            )
    return PersistedPosting(posting_id, existing is None, source_id, len(requirements))


def _insert(conn: sa.Connection, key: str, values: dict[str, Any]) -> int:
    statement = sa.insert(schema.job_posting).values(url=key, **values)
    return int(conn.execute(statement.returning(schema.job_posting.c.id)).scalar_one())
