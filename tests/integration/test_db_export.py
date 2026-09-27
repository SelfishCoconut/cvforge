"""NFR-09: one database file, and an export that restores to identical counts."""

from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.kb import apply, export, queries
from cvforge.kb.models import ProposalDraft
from cvforge.kb.vocab import SourceKind

pytestmark = pytest.mark.integration


def _populate(engine: sa.Engine) -> None:
    source = apply.record_source(engine, SourceKind.CONVERSATION, "synthetic")
    evidence = apply.record_evidence(engine, source, "message:1", "I used Rust at Acme.")
    draft = ProposalDraft.model_validate(
        {
            "origin": "chat",
            "source_id": source,
            "summary": "s",
            "operations": [
                {
                    "seq": 0,
                    "payload": {
                        "op_type": "create_entity",
                        "kind": "skill",
                        "name": "Rust",
                        "evidence_id": evidence,
                    },
                    "classification": "new",
                },
                {
                    "seq": 1,
                    "payload": {
                        "op_type": "create_entity",
                        "kind": "organization",
                        "name": "Acme",
                        "evidence_id": evidence,
                    },
                    "classification": "new",
                },
                {
                    "seq": 2,
                    "payload": {
                        "op_type": "add_edge",
                        "src": {"op": 0},
                        "rel": "at_organization",
                        "dst": {"op": 1},
                        "evidence_id": evidence,
                    },
                    "classification": "new",
                },
            ],
        }
    )
    proposal = apply.record_proposal(engine, draft)
    with engine.connect() as conn:
        record = queries.get_proposal(conn, proposal)
    assert record is not None
    for op in record.operations:
        apply.review_operation(engine, op.id, "accept")
    apply.commit_proposal(engine, proposal)


def test_the_running_app_uses_exactly_one_database_file(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/entities").status_code == 200
        on_disk = sorted(p.name for p in (tmp_path / "data").iterdir())
    assert on_disk == ["cvforge.db"]


def test_an_export_restores_to_the_same_counts(
    tmp_path: Path, open_db: Callable[..., sa.Engine]
) -> None:
    db = tmp_path / "data" / "cvforge.db"
    engine = open_db(db)
    _populate(engine)
    with engine.connect() as conn:
        original = queries.table_counts(conn)
    copy = export.export_database(db, tmp_path / "elsewhere" / "copy.db")
    with open_db(copy, migrated=False).connect() as conn:
        restored = queries.table_counts(conn)
    assert restored == original
    assert original["entity"] == 2 and original["edge"] == 1


def test_the_export_command_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, open_db: Callable[..., sa.Engine]
) -> None:
    monkeypatch.setenv("CVFORGE_DATA_DIR", str(tmp_path / "data"))
    open_db(tmp_path / "data" / "cvforge.db").dispose()
    target = tmp_path / "copy.db"
    assert export.main([str(target)]) == 0
    assert target.is_file()
    assert export.main([str(target)]) == 1


def test_exporting_a_missing_database_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CVFORGE_DATA_DIR", str(tmp_path / "nothing"))
    assert export.main([str(tmp_path / "copy.db")]) == 1
