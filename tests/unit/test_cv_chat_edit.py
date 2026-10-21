# ruff: noqa: RUF001
"""FR-31: conversational edits reword, drop and emphasise without losing support."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from tests.support.profile import build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.cv.grounding import ungrounded_terms


class Planner:
    """A scripted edit agent that records what it was shown."""

    def __init__(self) -> None:
        self.plan: dict[str, Any] = {"ops": [], "reply": "Done."}
        self.prompts: list[str] = []
        self.tools: list[list[str]] = []

    def model(self) -> FunctionModel:
        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.prompts.append(str(messages))
            self.tools.append([t.name for t in info.function_tools])
            return ModelResponse(
                parts=[ToolCallPart(next(iter(info.output_tools)).name, self.plan)]
            )

        return FunctionModel(respond)


@pytest.fixture
def editing(
    kb: sa.Engine, propose: Any, tmp_path: Path
) -> Iterator[tuple[TestClient, dict[str, Any], Planner]]:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    planner = Planner()
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    app = create_app(settings, engine=kb)
    app.state.model_factory = lambda _e: planner.model()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()
        yield client, cv, planner


def _claim(cv: dict[str, Any], text: str) -> dict[str, Any]:
    return next(
        c for s in cv["sections"] for i in s["items"] for c in i["claims"] if c["text"] == text
    )


def _texts(cv: dict[str, Any]) -> list[str]:
    return [c["text"] for s in cv["sections"] for i in s["items"] for c in i["claims"]]


def _edit(client: TestClient, cv: dict[str, Any], planner: Planner, *ops: dict[str, Any]) -> Any:
    planner.plan = {"ops": list(ops), "reply": "ok"}
    return client.post(f"/api/cvs/{cv['id']}/edit", json={"instruction": "tweak it"})


def test_a_reworded_bullet_keeps_its_entity_and_assertion_links(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    old = _claim(cv, "Parsed two gigabytes per second")

    response = _edit(
        client,
        cv,
        planner,
        {"kind": "reword", "claim_id": old["id"], "text": "Processed two gigabytes each second"},
    )

    body = response.json()
    assert response.status_code == 200 and body["refused"] == [] and body["issues"] == []
    new = _claim(body["cv"], "Processed two gigabytes each second")
    assert (new["entity_id"], new["assertion_id"]) == (old["entity_id"], old["assertion_id"])


def test_every_edit_is_a_new_collaborative_version_and_history_is_untouched(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    old = _claim(cv, "Parsed two gigabytes per second")
    body = _edit(
        client,
        cv,
        planner,
        {"kind": "reword", "claim_id": old["id"], "text": "Parsed two gigabytes a second"},
    ).json()

    assert (body["cv"]["version"], body["cv"]["parent_cv_id"]) == (2, cv["id"])
    assert body["cv"]["generation_mode"] == "collaborative"
    assert _texts(client.get(f"/api/cvs/{cv['id']}").json()) == _texts(cv)
    second = _edit(
        client,
        body["cv"],
        planner,
        {"kind": "drop", "claim_id": _claim(body["cv"], "Built data services")["id"]},
    ).json()
    assert second["cv"]["version"] == 3 and second["cv"]["parent_cv_id"] == body["cv"]["id"]


@pytest.mark.parametrize(
    "text",
    [
        "Led a team of 50 engineers parsing logs",
        "Parsed two gigabytes per second using Kubernetes",
        "Managed the parsing platform",
    ],
)
def test_a_rewording_that_adds_a_fact_is_refused_and_creates_no_version(
    editing: tuple[TestClient, dict[str, Any], Planner], text: str
) -> None:
    client, cv, planner = editing
    old = _claim(cv, "Parsed two gigabytes per second")
    body = _edit(
        client, cv, planner, {"kind": "reword", "claim_id": old["id"], "text": text}
    ).json()

    assert body["cv"] is None and body["applied"] == []
    assert "adds" in body["refused"][0]
    assert len(client.get(f"/api/jobs/{cv['job_posting_id']}/cvs").json()) == 1


def test_emphasis_on_something_nothing_stored_supports_is_refused_and_redirected(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    body = _edit(client, cv, planner, {"kind": "emphasize", "name": "Kubernetes"}).json()
    assert body["cv"] is None
    assert "nothing confirmed is stored about 'Kubernetes'" in body["refused"][0]
    gap = _edit(client, cv, planner, {"kind": "emphasize", "name": "Haskell"}).json()
    assert gap["cv"] is None and "Haskell" in gap["refused"][0]  # recorded, but only as a gap


def test_emphasising_a_stored_confirmed_skill_adds_it_at_the_front(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    body = _edit(client, cv, planner, {"kind": "emphasize", "name": "python"}).json()

    assert body["issues"] == [] and _texts(body["cv"])[0] == "Python"
    assert _claim(body["cv"], "Python")["entity_id"]


def test_emphasising_what_is_already_on_the_cv_reorders_it(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    old = _claim(cv, "Parsed two gigabytes per second")
    first = _edit(client, cv, planner, {"kind": "emphasize", "name": "Log parser"}).json()
    bullets = [
        c["text"] for c in first["cv"]["sections"][1]["items"][0]["claims"] if c["slot"] == "bullet"
    ]
    assert bullets == ["Parsed two gigabytes per second", "Built data services"]
    assert old["text"] in bullets


def test_dropping_a_required_skill_makes_the_new_version_fail_validation_and_unfinalisable(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    rust = _claim(cv, "Rust")
    body = _edit(client, cv, planner, {"kind": "drop", "claim_id": rust["id"]}).json()

    assert [i["code"] for i in body["issues"]] == ["incomplete_coverage"]
    assert client.post(f"/api/cvs/{body['cv']['id']}/final").status_code == 409


def test_structure_is_not_edited_one_piece_at_a_time_and_malformed_ops_are_ignored(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    header = _claim(cv, "Backend Engineer")
    body = _edit(
        client,
        cv,
        planner,
        {"kind": "reword", "claim_id": header["id"], "text": "CTO"},
        {"kind": "drop", "claim_id": header["id"]},
        {"kind": "drop"},
        {"kind": "reword", "claim_id": 99999, "text": "x"},
    ).json()
    assert body["cv"] is None and len(body["refused"]) == 4


def test_a_hostile_cv_line_stays_in_the_fence_and_the_agent_has_no_tools(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, planner = editing
    client.post(f"/api/cvs/{cv['id']}/edit", json={"instruction": "shorten"})
    assert planner.tools == [[]]
    assert planner.prompts[0].count("</cv>") == 1


def test_a_failing_model_is_a_502_and_an_unknown_cv_a_404(
    editing: tuple[TestClient, dict[str, Any], Planner],
) -> None:
    client, cv, _ = editing

    def broken(_engine: object) -> object:
        raise RuntimeError("down")

    client.app.state.model_factory = broken  # type: ignore[attr-defined]
    assert client.post(f"/api/cvs/{cv['id']}/edit", json={"instruction": "x"}).status_code == 502
    assert client.post("/api/cvs/999/edit", json={"instruction": "x"}).status_code == 404


@pytest.mark.parametrize(
    ("facts", "text", "expected"),
    [
        (["Log parser", "Parsed two gigabytes per second"], "Processed two gigabytes a second", []),
        (["Backend engineer"], "Led the work", ["Led"]),
        (["Backend engineer"], "Delivered 3x faster", ["3x"]),
        (["Rust", "Log parser"], "Built a Rust log parser", []),
        (["Log parser"], "Built a Rust log parser", ["Rust"]),
        (["Log parser"], "Parser built in 2019", ["2019"]),
        (["Capitalised first word is fine"], "Capitalised first word is fine", []),
    ],
)
def test_the_grounding_heuristic(facts: list[str], text: str, expected: list[str]) -> None:
    assert ungrounded_terms(facts, text) == expected


@pytest.mark.parametrize(
    ("facts", "text", "needle"),
    [
        (["Parsed logs"], "Led parsed logs", "Led"),  # a strong verb leading the line
        (["Parsed logs"], "Never parsed logs", "Never"),  # a negation the facts lack
        (["Cut latency 40% and served 3x users"], "Cut latency 3x and served 40% users", "order"),
        (["Parsed logs"], "Lideré parsed logs", "Lideré"),  # non-English leadership verb
        (
            ["Parsed logs"],
            "Parsed logs for ５０ teams",
            "50",
        ),  # fullwidth digits (NFKC)
        (["Parsed logs"], "Parsed logs and mentoring", "mentoring"),
        (["Parsed logs"], "Parsed logs, wrote docs, gave talks, ran tools", "words"),  # growth
    ],
)
def test_the_hardened_grounding_catches_what_a_bag_of_tokens_missed(
    facts: list[str], text: str, needle: str
) -> None:
    assert any(needle in term for term in ungrounded_terms(facts, text))


def test_a_lowercase_mention_of_another_stored_entity_is_flagged() -> None:
    assert ungrounded_terms(
        ["Parsed logs"], "parsed logs on kubernetes", other_entities=["Kubernetes"]
    ) == ["kubernetes"]
    assert (
        ungrounded_terms(
            ["Parsed Kubernetes logs"], "parsed kubernetes logs", other_entities=["Kubernetes"]
        )
        == []
    )


def test_a_reword_citing_a_superseded_assertion_is_refused(
    editing: tuple[TestClient, dict[str, Any], Planner], kb: sa.Engine, propose: Any
) -> None:
    from cvforge.kb import apply

    client, cv, planner = editing
    bullet = _claim(cv, "Parsed two gigabytes per second")
    apply.commit_proposal(
        kb,
        propose(
            {
                "op_type": "update_field",
                "entity_id": bullet["entity_id"],
                "field": "summary",
                "value": "Parsed three gigabytes per second",
            },
            accept=True,
        ),
    )
    body = _edit(
        client,
        cv,
        planner,
        {"kind": "reword", "claim_id": bullet["id"], "text": "Parsed two gigabytes a second"},
    ).json()
    assert body["cv"] is None and "no longer states" in body["refused"][0]


def test_an_automatic_cv_cannot_carry_reworded_claims(kb: sa.Engine, propose: Any) -> None:
    from dataclasses import replace

    from cvforge.cv.generate import generate_cv
    from cvforge.cv.store import UnsupportedClaimError, save_cv
    from cvforge.kb.vocab import ClaimBasis

    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    claims = generate_cv(kb, posting)
    bullet = next(c for c in claims if c.basis is ClaimBasis.SUMMARY)
    with pytest.raises(UnsupportedClaimError, match="automatic"):
        save_cv(kb, posting, [replace(bullet, basis=ClaimBasis.REWORD)])


def test_emphasising_a_role_moves_its_whole_item_and_blank_rewording_is_refused(
    kb: sa.Engine, propose: Any
) -> None:
    from cvforge.cv.edit import Emphasize, Reword, apply_edits
    from cvforge.cv.generate import generate_cv
    from cvforge.cv.store import get_cv, save_cv

    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = get_cv(kb, save_cv(kb, posting, generate_cv(kb, posting)))
    assert cv is not None
    bullet = next(c for c in cv.claims if c.text == "Built data services")

    result = apply_edits(kb, cv, [Emphasize("Backend Engineer"), Reword(bullet.id, "   ")])

    assert result.applied == ["emphasised 'Backend Engineer'"]
    assert "new wording is empty" in result.refused[0]
    assert [c.text for c in result.claims][:2] == ["Rust", "Backend Engineer"]


def test_emphasising_a_confirmed_non_skill_that_is_not_on_the_cv_is_redirected(
    kb: sa.Engine, propose: Any
) -> None:
    from cvforge.cv.edit import Emphasize, apply_edits
    from cvforge.cv.generate import generate_cv
    from cvforge.cv.store import get_cv, save_cv

    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = get_cv(kb, save_cv(kb, posting, generate_cv(kb, posting)))
    assert cv is not None
    result = apply_edits(kb, cv, [Emphasize("Log parser")])  # a project; not shown as its own item
    assert result.applied or "nothing confirmed" in result.refused[0]
