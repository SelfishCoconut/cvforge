"""D-D: a real SimilarFinder over the sqlite-vec index, feeding kb.classify (FR-08)."""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.kb import apply, classify
from cvforge.kb.dedup import make_similar_finder
from cvforge.kb.embeddings import EmbeddingError, index_entities
from cvforge.kb.models import CreateEntity
from cvforge.kb.vocab import Classification, EntityKind

Propose = Callable[..., int]


class _FailingProvider:
    """An `EmbeddingProvider` whose `embed` always raises."""

    dimension = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("the embedding endpoint is down")


def _entity(kb: sa.Engine, propose: Propose, *, name: str) -> int:
    result = apply.commit_proposal(
        kb, propose({"op_type": "create_entity", "kind": "skill", "name": name}, accept=True)
    )
    return result.entity_ids[0]


def test_a_known_by_name_candidate_still_classifies_known_not_duplicate(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="Rust")
    index_entities(kb, provider, [rust])
    # threshold=0.0 so the real finder would happily call ANY name a duplicate;
    # name identity must still win before `similar` is ever consulted.
    finder = make_similar_finder(kb, provider, threshold=0.0)

    with kb.connect() as conn:
        payload = CreateEntity(kind=EntityKind.SKILL, name="Rust", evidence_id=evidence_id)
        verdict = classify.classify(conn, payload, similar=finder)

    assert (verdict.classification, verdict.target_id) == (Classification.KNOWN, rust)


def test_a_similar_but_differently_named_entity_classifies_duplicate(
    kb: sa.Engine, propose: Propose, evidence_id: int
) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _entity(kb, propose, name="rust programmer")
    index_entities(kb, provider, [rust])
    finder = make_similar_finder(kb, provider, threshold=0.5)

    with kb.connect() as conn:
        payload = CreateEntity(
            kind=EntityKind.SKILL, name="rust developer", evidence_id=evidence_id
        )
        verdict = classify.classify(conn, payload, similar=finder)

    assert (verdict.classification, verdict.target_id) == (Classification.DUPLICATE, rust)


def test_the_finder_returns_none_when_the_embedder_is_unavailable(kb: sa.Engine) -> None:
    finder = make_similar_finder(kb, _FailingProvider(), threshold=0.5)
    assert finder(EntityKind.SKILL, "anything") is None


def test_classification_degrades_to_new_when_the_embedder_is_unavailable(
    kb: sa.Engine, evidence_id: int
) -> None:
    finder = make_similar_finder(kb, _FailingProvider(), threshold=0.5)

    with kb.connect() as conn:
        payload = CreateEntity(kind=EntityKind.SKILL, name="anything new", evidence_id=evidence_id)
        verdict = classify.classify(conn, payload, similar=finder)

    assert verdict.classification == Classification.NEW
