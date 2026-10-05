"""Agents expose only read tools, and the read tools read correctly (FR-06)."""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from cvforge.kb import apply, embeddings
from cvforge.kb.embeddings import EmbeddingError
from cvforge.kb.vocab import EntityKind
from cvforge.llm import tools
from cvforge.llm.agents import AGENTS
from cvforge.llm.tools import READ_TOOLS, KbDeps


class _Embedder:
    dimension = 3

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingError("down")
        return [[1.0, 0.0, 0.0] for _ in texts]


def _commit(kb: sa.Engine, propose: Any, *payloads: dict[str, Any]) -> None:
    apply.commit_proposal(kb, propose(*payloads, accept=True))


def _ctx(engine: sa.Engine, embedder: Any = None) -> RunContext[KbDeps]:
    return RunContext(deps=KbDeps(engine, embedder), model=TestModel(), usage=RunUsage())


def test_every_registered_agent_exposes_only_read_tools(kb: sa.Engine) -> None:
    for name, build in AGENTS.items():
        model = TestModel()
        build(model).run_sync("hello", deps=KbDeps(kb, None))
        params = model.last_model_request_parameters
        assert params is not None
        offered = {tool.name for tool in params.function_tools}
        assert offered == READ_TOOLS, name


def test_search_and_get_entity(kb: sa.Engine, propose: Any) -> None:
    _commit(kb, propose, {"op_type": "create_entity", "kind": "skill", "name": "Rust"})
    ctx = _ctx(kb)

    (hit,) = tools.search_entities(ctx, "rus")
    assert hit["name"] == "Rust"
    assert tools.search_entities(ctx, "rus", EntityKind.ROLE) == []
    entity = tools.get_entity(ctx, hit["id"])
    assert entity is not None and entity["kind"] == "skill"
    assert tools.get_entity(ctx, 9999) is None


def test_neighbours_lists_edges(kb: sa.Engine, propose: Any) -> None:
    _commit(
        kb,
        propose,
        {"op_type": "create_entity", "kind": "skill", "name": "Rust"},
        {"op_type": "create_entity", "kind": "project", "name": "Parser"},
        {"op_type": "add_edge", "src": {"op": 0}, "rel": "used_in", "dst": {"op": 1}},
    )
    (hit,) = tools.search_entities(_ctx(kb), "rust")

    (edge,) = tools.neighbours(_ctx(kb), hit["id"])

    assert edge["rel"] == "used_in"


def test_find_similar_degrades_to_empty(kb: sa.Engine) -> None:
    assert tools.find_similar(_ctx(kb), "Rust") == []
    assert tools.find_similar(_ctx(kb, _Embedder(fail=True)), "Rust") == []


def test_find_similar_returns_hits(kb: sa.Engine, propose: Any) -> None:
    _commit(kb, propose, {"op_type": "create_entity", "kind": "skill", "name": "Rust"})
    embedder = _Embedder()
    embeddings.reindex_missing(kb, embedder)

    (hit,) = tools.find_similar(_ctx(kb, embedder), "Rust lang")

    assert hit["name"] == "Rust"
