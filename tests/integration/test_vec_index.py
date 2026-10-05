"""FR-05 / D-D: the sqlite-vec index against a real file-backed database."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.kb import apply, queries
from cvforge.kb.embeddings import find_similar, index_entities, reindex_missing
from cvforge.kb.models import ProposalInput
from cvforge.kb.vocab import SourceKind

pytestmark = pytest.mark.integration

OpenDb = Callable[..., sa.Engine]


def _create_entity(engine: sa.Engine, name: str) -> int:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", name)
    draft = ProposalInput.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "s",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "evidence_id": evidence,
                        "op_type": "create_entity",
                        "kind": "skill",
                        "name": name,
                    },
                }
            ],
        }
    )
    proposal_id = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal_id)
    assert record is not None
    for op in record.operations:
        apply.review_operation(engine, op.id, "accept")
    result = apply.commit_proposal(engine, proposal_id)
    return result.entity_ids[0]


def test_a_dimension_change_rebuilds_the_index_and_reembeds(
    tmp_path: Path, open_db: OpenDb
) -> None:
    db = open_db(tmp_path / "cvforge.db")
    small = FakeEmbeddingProvider(dimension=8)
    rust = _create_entity(db, "rust programmer")
    index_entities(db, small, [rust])
    assert find_similar(db, small, "rust developer", threshold=0.5) != []

    large = FakeEmbeddingProvider(dimension=16)
    reindexed = reindex_missing(db, large)

    assert reindexed == 1
    hits = find_similar(db, large, "rust developer", threshold=0.5)
    assert [hit.entity_id for hit in hits] == [rust]


def test_the_index_persists_across_a_reopen(tmp_path: Path, open_db: OpenDb) -> None:
    path = tmp_path / "cvforge.db"
    db = open_db(path)
    provider = FakeEmbeddingProvider(dimension=8)
    rust = _create_entity(db, "rust programmer")
    index_entities(db, provider, [rust])

    reopened = open_db(path)
    hits = find_similar(reopened, provider, "rust developer", threshold=0.5)
    assert [hit.entity_id for hit in hits] == [rust]
