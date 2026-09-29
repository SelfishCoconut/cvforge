"""FR-05: sqlite-vec similarity search over entities (D-D)."""

from collections.abc import Callable, Sequence

import pytest
import sqlalchemy as sa
from sqlite_vec import serialize_float32
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.kb import apply
from cvforge.kb.embeddings import (
    EmbeddingError,
    SimilarHit,
    ensure_index,
    find_similar,
    index_entities,
    reindex_missing,
)
from cvforge.kb.vocab import EntityKind

Propose = Callable[..., int]


class _FailingProvider:
    """An `EmbeddingProvider` whose `embed` always raises."""

    dimension = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("the embedding endpoint is down")


def _entity(kb: sa.Engine, propose: Propose, *, kind: str = "skill", name: str) -> int:
    result = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": kind, "name": name}, accept=True)
    )
    return result.entity_ids[0]


class _UnprobeableProvider:
    """An embedder that is down before its dimension has ever been probed."""

    @property
    def dimension(self) -> int:
        raise EmbeddingError("cannot probe the dimension")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("the embedding endpoint is down")


def test_index_entities_reports_ids_when_the_dimension_probe_fails(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _entity(kb, propose, name="rust programmer")

    assert index_entities(kb, _UnprobeableProvider(), [rust]) == [rust]


def test_a_non_positive_dimension_is_refused_before_any_sql(kb: sa.Engine) -> None:
    with pytest.raises(ValueError, match="positive"):
        ensure_index(kb, 0)


def test_find_similar_ranks_a_candidate_above_the_threshold(
    kb: sa.Engine, propose: Propose
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [rust])

    hits = find_similar(kb, provider, "rust developer", threshold=0.5)

    assert hits == [SimilarHit(entity_id=rust, name="rust programmer", score=hits[0].score)]
    assert hits[0].score > 0.5


def test_an_empty_index_returns_no_hits_without_raising(kb: sa.Engine) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    assert find_similar(kb, provider, "anything") == []


def test_a_candidate_below_the_threshold_is_absent(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    unrelated = _entity(kb, propose, name="banana bread recipe")
    index_entities(kb, provider, [unrelated])

    assert find_similar(kb, provider, "rust programmer", threshold=0.9) == []


def test_kind_filters_a_similar_entity_of_another_kind(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    project = _entity(kb, propose, kind="project", name="rust programmer")
    index_entities(kb, provider, [project])

    assert find_similar(kb, provider, "rust programmer", kind=EntityKind.SKILL, threshold=0.5) == []
    matches = find_similar(kb, provider, "rust programmer", kind=EntityKind.PROJECT, threshold=0.5)
    assert [hit.entity_id for hit in matches] == [project]


def test_index_entities_with_a_failing_provider_returns_the_failed_ids(
    kb: sa.Engine, propose: Propose
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    kept = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [kept])
    new = _entity(kb, propose, name="python developer")

    failed = index_entities(kb, _FailingProvider(), [new])

    assert failed == [new]


def test_a_failing_embed_leaves_existing_rows_intact(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    kept = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [kept])
    new = _entity(kb, propose, name="python developer")

    index_entities(kb, _FailingProvider(), [new])

    hits = find_similar(kb, provider, "rust programmer", threshold=0.5)
    assert [hit.entity_id for hit in hits] == [kept]


def test_find_similar_with_a_failing_provider_raises_embedding_error(kb: sa.Engine) -> None:
    with pytest.raises(EmbeddingError):
        find_similar(kb, _FailingProvider(), "anything")


def test_index_entities_with_an_id_that_does_not_exist_reports_it_missing(kb: sa.Engine) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    assert index_entities(kb, provider, [999]) == [999]


def test_indexing_embeds_the_summary_too_not_just_the_name(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    entity_id = apply.commit_proposal(
        kb,
        propose(
            {
                "op_type": "create_entity",
                "kind": "skill",
                "name": "Systems programming",
                "summary": "distributed systems",
            },
            accept=True,
        ),
    ).entity_ids[0]
    index_entities(kb, provider, [entity_id])

    hits = find_similar(kb, provider, "distributed", threshold=0.4)

    assert [hit.entity_id for hit in hits] == [entity_id]


def test_reindex_missing_is_a_no_op_once_everything_is_indexed(
    kb: sa.Engine, propose: Propose
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [rust])

    assert reindex_missing(kb, provider) == 0


def test_reindex_missing_never_probes_the_embedder_when_there_is_nothing_to_index(
    kb: sa.Engine,
) -> None:
    class _TripwireProvider:
        @property
        def dimension(self) -> int:
            raise AssertionError("dimension should not be read when there is nothing to index")

        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise AssertionError("embed should not be called when there is nothing to index")

    assert reindex_missing(kb, _TripwireProvider()) == 0


def test_find_similar_truncates_to_limit(kb: sa.Engine, propose: Propose) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    ids = [_entity(kb, propose, name=f"rust programmer {i}") for i in range(3)]
    index_entities(kb, provider, ids)

    hits = find_similar(kb, provider, "rust programmer", threshold=0.0, limit=2)

    assert len(hits) == 2


def test_index_entities_mixes_a_failing_provider_and_a_missing_entity(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _entity(kb, propose, name="rust programmer")

    assert sorted(index_entities(kb, _FailingProvider(), [rust, 9999])) == [rust, 9999]


def test_a_missing_entity_is_reported_and_a_real_one_is_still_indexed(
    kb: sa.Engine, propose: Propose
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="rust programmer")

    assert index_entities(kb, provider, [rust, 9999]) == [9999]
    assert [h.entity_id for h in find_similar(kb, provider, "rust programmer", threshold=0.5)] == [
        rust
    ]


def test_an_orphan_index_row_is_skipped_and_does_not_hide_a_real_hit(
    kb: sa.Engine, propose: Propose
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [rust])
    (vector,) = provider.embed(["rust programmer"])
    with kb.begin() as conn:  # an index row whose entity no longer exists
        conn.exec_driver_sql(
            "INSERT INTO entity_vec(entity_id, embedding) VALUES (?, ?)",
            (9999, serialize_float32(vector)),
        )

    hits = find_similar(kb, provider, "rust programmer", threshold=0.5)

    assert [h.entity_id for h in hits] == [rust]
