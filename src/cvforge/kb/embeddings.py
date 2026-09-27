"""Pluggable text embedding providers and sqlite-vec similarity search (FR-40, FR-05).

The knowledge base never depends on a specific embedding backend directly: it
depends on `EmbeddingProvider`, so a different model or a different dimension
is a settings change, not a code change.

`ensure_index`, `index_entities` and `reindex_missing` are registered writers of
`entity_vec` (ADR-0011): a `vec0` virtual table holding one row per indexed
entity. It is derived, disposable state, never a source of provenance — if it
is dropped, `reindex_missing` rebuilds it from the entities that already exist.
Reads of entity data go through `kb.queries`, never `kb.schema` directly, so
this module is never seen referencing a knowledge table.
"""

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx
import sqlalchemy as sa
from sqlite_vec import serialize_float32

from cvforge.kb import queries
from cvforge.kb.vocab import EntityKind


class EmbeddingError(Exception):
    """An embedding call failed: the network, the endpoint, or the model itself."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Something that turns text into fixed-length vectors."""

    @property
    def dimension(self) -> int:
        """The length of every vector this provider returns."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each of `texts`, in order.

        Args:
            texts: The strings to embed.

        Returns:
            One vector of length `dimension` per input text, same order.

        Raises:
            EmbeddingError: If the provider could not embed the batch.
        """
        ...


class OllamaEmbeddingProvider:
    """Embeds text through a local Ollama server's `/api/embed` endpoint."""

    def __init__(self, base_url: str, model: str, *, client: httpx.Client | None = None) -> None:
        """Build a provider bound to one Ollama server and model.

        Args:
            base_url: The bare Ollama host, e.g. `http://127.0.0.1:11434` (no
                trailing `/api/...`).
            model: The embedding model name Ollama should load.
            client: An `httpx.Client` to use instead of building one; tests
                inject a client over `httpx.MockTransport`.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client()
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        """The vector length, probed once with a one-word embed call and cached."""
        if self._dimension is None:
            self._dimension = len(self.embed(["."])[0])
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """POST `{base_url}/api/embed` and return the embeddings it reports.

        Args:
            texts: The strings to embed.

        Returns:
            One vector per input text, same order as Ollama returned them.

        Raises:
            EmbeddingError: On any transport error or non-2xx response.
        """
        try:
            response = self._client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": list(texts)},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding call to {self._base_url} failed: {exc}") from exc
        return list(response.json()["embeddings"])


_TABLE = "entity_vec"
_DIMENSION_PATTERN = re.compile(r"float\[(\d+)\]", re.I)


@dataclass(frozen=True)
class SimilarHit:
    """One candidate match, ranked by how close it is to the query text."""

    entity_id: int
    name: str
    score: float


def _current_dimension(conn: sa.Connection) -> int | None:
    """The vector length `_TABLE` was created with, or None if it doesn't exist yet."""
    row = conn.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (_TABLE,)
    ).fetchone()
    if row is None:
        return None
    match = _DIMENSION_PATTERN.search(row[0])
    return int(match.group(1)) if match else None


@contextmanager
def _write_transaction(engine: sa.Engine) -> Iterator[sa.Connection]:
    """BEGIN IMMEDIATE before any read.

    Mirrors `kb.apply._write_transaction`'s rationale (see its docstring):
    `ensure_index` decides whether to rebuild from what it reads, so the read
    and the rebuild must share one lock or two concurrent callers can race.

    Args:
        engine: The knowledge-base engine.

    Yields:
        A connection inside the transaction. It is committed when the block ends
        and rolled back if the block raises.
    """
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()


def ensure_index(engine: sa.Engine, dimension: int) -> None:
    """Create the similarity index, or rebuild it if its recorded dimension differs (D-D).

    Args:
        engine: The knowledge-base engine.
        dimension: The vector length every row must have.
    """
    with _write_transaction(engine) as conn:
        if _current_dimension(conn) == dimension:
            return
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_TABLE}")
        conn.exec_driver_sql(
            f"CREATE VIRTUAL TABLE {_TABLE} USING vec0("
            f"entity_id INTEGER PRIMARY KEY, embedding FLOAT[{dimension}] "
            "DISTANCE_METRIC=cosine)"
        )


def _indexed_ids(conn: sa.Connection) -> set[int]:
    # `_TABLE` is the fixed module constant "entity_vec", never external input.
    return {row[0] for row in conn.exec_driver_sql(f"SELECT entity_id FROM {_TABLE}")}  # noqa: S608


def index_entities(
    engine: sa.Engine, provider: EmbeddingProvider, entity_ids: Sequence[int]
) -> list[int]:
    """Embed and (re)index each of `entity_ids`. Never raises `EmbeddingError`.

    Args:
        engine: The knowledge-base engine.
        provider: What turns a name into a vector.
        entity_ids: The ids to (re)index.

    Returns:
        The ids that failed to embed; every other id's row is written or kept
        exactly as it was.
    """
    ensure_index(engine, provider.dimension)
    with engine.connect() as conn:
        records = [queries.get_entity(conn, eid) for eid in entity_ids]
    present = [(eid, r.name) for eid, r in zip(entity_ids, records, strict=True) if r is not None]
    missing = [eid for eid, r in zip(entity_ids, records, strict=True) if r is None]
    if not present:
        return missing
    try:
        vectors = provider.embed([name for _, name in present])
    except EmbeddingError:
        return [eid for eid, _name in present] + missing
    with _write_transaction(engine) as conn:
        for (eid, _name), vector in zip(present, vectors, strict=True):
            # `_TABLE` is the fixed constant "entity_vec", never external input.
            conn.exec_driver_sql(
                f"INSERT OR REPLACE INTO {_TABLE}(entity_id, embedding) VALUES (?, ?)",  # noqa: S608
                (eid, serialize_float32(vector)),
            )
    return missing


def reindex_missing(engine: sa.Engine, provider: EmbeddingProvider) -> int:
    """(Re)index every entity the similarity index doesn't yet cover.

    Args:
        engine: The knowledge-base engine.
        provider: What turns a name into a vector.

    Returns:
        How many entities were newly indexed.
    """
    ensure_index(engine, provider.dimension)
    with engine.connect() as conn:
        all_ids = {record.id for record in queries.list_entities(conn)}
        already_indexed = _indexed_ids(conn)
    to_index = sorted(all_ids - already_indexed)
    if not to_index:
        return 0
    failed = index_entities(engine, provider, to_index)
    return len(to_index) - len(failed)


def find_similar(
    engine: sa.Engine,
    provider: EmbeddingProvider,
    text: str,
    *,
    kind: EntityKind | None = None,
    threshold: float = 0.85,
    limit: int = 5,
) -> list[SimilarHit]:
    """Rank existing entities by cosine similarity to `text` (FR-05).

    Args:
        engine: The knowledge-base engine.
        provider: What turns `text` and every candidate's name into a vector.
        text: The candidate name or summary to compare against.
        kind: Only consider entities of this kind.
        threshold: The minimum cosine similarity to report, in [0, 1].
        limit: The maximum number of hits to return.

    Returns:
        Hits at or above `threshold`, best first, at most `limit`.

    Raises:
        EmbeddingError: If `text` could not be embedded.
    """
    ensure_index(engine, provider.dimension)
    (vector,) = provider.embed([text])
    hits: list[SimilarHit] = []
    with engine.connect() as conn:
        # `_TABLE` is the fixed constant "entity_vec" on both queries below, never
        # external input.
        row_count = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {_TABLE}").scalar()  # noqa: S608
        if row_count == 0:
            return hits
        rows = conn.exec_driver_sql(
            f"SELECT entity_id, distance FROM {_TABLE} WHERE embedding MATCH ? "  # noqa: S608
            "AND k = ? ORDER BY distance",
            (serialize_float32(vector), row_count),
        ).fetchall()
        for entity_id, distance in rows:
            score = 1.0 - distance
            if score < threshold:
                continue
            record = queries.get_entity(conn, entity_id)
            if record is None or (kind is not None and record.kind is not kind):
                continue
            hits.append(SimilarHit(entity_id=entity_id, name=record.name, score=score))
            if len(hits) >= limit:
                break
    return hits
