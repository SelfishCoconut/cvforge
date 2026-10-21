"""FR-21: each requirement gets one of the four verdicts, decided by the database."""

from collections.abc import Sequence
from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.fake_embeddings import FakeEmbeddingProvider

from cvforge.jobs.store import persist_posting
from cvforge.kb import apply, embeddings
from cvforge.kb.embeddings import EmbeddingError
from cvforge.kb.vocab import MatchVerdict
from cvforge.llm.schemas import JobAnalysis
from cvforge.match.store import list_matches, replace_matches
from cvforge.match.verdicts import Candidate, Judgment, match_posting, match_requirement
from cvforge.web.fetch import FetchedPage

Propose = Any


def _entity(name: str, kind: str = "skill", state: str = "confirmed") -> dict[str, Any]:
    return {"op_type": "create_entity", "kind": kind, "name": name, "state": state}


def _record(kb: sa.Engine, propose: Propose, *payloads: dict[str, Any]) -> list[int]:
    """Commit `payloads`; returns the new entity ids in order."""
    result = apply.commit_proposal(kb, propose(*payloads, accept=True))
    return [result.entity_ids[i] for i in sorted(result.entity_ids)]


def _used(kb: sa.Engine, propose: Propose, skill: str, state: str = "confirmed") -> int:
    skill_id, project_id = _record(
        kb, propose, _entity(skill, state=state), _entity(f"{skill} project", "project")
    )
    apply.commit_proposal(
        kb,
        propose(
            {"op_type": "add_edge", "src": skill_id, "rel": "used_in", "dst": project_id},
            accept=True,
        ),
    )
    return skill_id


def test_a_confirmed_entity_with_a_recorded_use_is_satisfied(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _used(kb, propose, "Rust")
    outcome = match_requirement(kb, "rust")
    assert outcome.verdict is MatchVerdict.SATISFIED
    assert outcome.support == (rust,) and outcome.score == 1.0
    assert "recorded use" in outcome.rationale


def test_a_recorded_entity_with_no_recorded_use_is_undocumented_never_satisfied(
    kb: sa.Engine, propose: Propose
) -> None:
    _record(kb, propose, _entity("Haskell"))
    outcome = match_requirement(kb, "Haskell")
    assert outcome.verdict is MatchVerdict.UNDOCUMENTED and outcome.support == ()


@pytest.mark.parametrize("state", ["gap", "learning"])
def test_a_skill_recorded_as_gap_or_learning_is_a_gap(
    kb: sa.Engine, propose: Propose, state: str
) -> None:
    _used(kb, propose, "Kubernetes", state=state)
    outcome = match_requirement(kb, "Kubernetes")
    assert outcome.verdict is MatchVerdict.GAP and outcome.support == ()


def test_an_archived_entity_does_not_count(kb: sa.Engine, propose: Propose) -> None:
    _used(kb, propose, "Perl", state="archived")
    assert match_requirement(kb, "Perl").verdict is MatchVerdict.GAP


def test_nothing_recorded_and_no_similarity_is_a_gap(kb: sa.Engine) -> None:
    outcome = match_requirement(kb, "Fortran")
    assert outcome.verdict is MatchVerdict.GAP and outcome.score is None


def _indexed(kb: sa.Engine, *ids: int) -> FakeEmbeddingProvider:
    provider = FakeEmbeddingProvider()
    assert embeddings.index_entities(kb, provider, list(ids)) == []
    return provider


def test_a_close_used_entity_backs_the_requirement_as_evidenced(
    kb: sa.Engine, propose: Propose
) -> None:
    django = _used(kb, propose, "Django web framework")
    provider = _indexed(kb, django)
    outcome = match_requirement(kb, "web framework django", embedder=provider, threshold=0.85)
    assert outcome.verdict is MatchVerdict.EVIDENCED
    assert outcome.support == (django,) and "close to" in outcome.rationale


class _Judge:
    def __init__(self, ids: tuple[int, ...] = (), rationale: str = "implied") -> None:
        self.ids, self.rationale = ids, rationale
        self.seen: list[Sequence[Candidate]] = []

    def judge(self, requirement: str, candidates: Sequence[Candidate]) -> Judgment:
        self.seen.append(candidates)
        return Judgment(self.ids or tuple(c.entity_id for c in candidates), self.rationale)


def _adjacent(kb: sa.Engine, propose: Propose) -> tuple[int, FakeEmbeddingProvider]:
    entity = _used(kb, propose, "Django REST API")
    return entity, _indexed(kb, entity)


def test_a_judged_inference_is_evidenced_with_the_judges_rationale(
    kb: sa.Engine, propose: Propose
) -> None:
    entity, provider = _adjacent(kb, propose)
    outcome = match_requirement(
        kb, "REST API client", embedder=provider, judge=_Judge(rationale="Django REST implies it")
    )
    assert outcome.verdict is MatchVerdict.EVIDENCED
    assert outcome.support == (entity,) and outcome.rationale == "Django REST implies it"


@pytest.mark.parametrize(
    "judge",
    [_Judge(ids=(999,)), _Judge(rationale="  "), None],
    ids=["invented-id", "blank-rationale", "no-judge"],
)
def test_an_unvalidated_or_missing_judgment_leaves_the_requirement_undocumented(
    kb: sa.Engine, propose: Propose, judge: _Judge | None
) -> None:
    _, provider = _adjacent(kb, propose)
    outcome = match_requirement(kb, "REST API client", embedder=provider, judge=judge)
    assert outcome.verdict is MatchVerdict.UNDOCUMENTED
    assert outcome.support == () and outcome.score is not None


def test_a_judge_is_only_offered_used_confirmed_candidates(kb: sa.Engine, propose: Propose) -> None:
    _record(kb, propose, _entity("Django REST API"))  # recorded, never used
    provider = _indexed(kb, 1)
    judge = _Judge()
    outcome = match_requirement(kb, "REST API client", embedder=provider, judge=judge)
    assert judge.seen == [] and outcome.verdict is MatchVerdict.UNDOCUMENTED


def test_an_embedding_failure_degrades_to_gap_and_says_so(kb: sa.Engine) -> None:
    class Broken(FakeEmbeddingProvider):
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise EmbeddingError("down")

    outcome = match_requirement(kb, "Anything", embedder=Broken())
    assert outcome.verdict is MatchVerdict.GAP and "unavailable" in outcome.rationale


def _posting(kb: sa.Engine, *skills: str) -> int:
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "text", "static")
    return persist_posting(kb, page, JobAnalysis(required_skills=list(skills))).id


def test_every_requirement_of_a_posting_gets_a_verdict_and_unknown_postings_none(
    kb: sa.Engine, propose: Propose
) -> None:
    _used(kb, propose, "Rust")
    posting = _posting(kb, "Rust", "Fortran")

    results = match_posting(kb, posting)

    assert results is not None
    assert [o.verdict for _, o in results] == [MatchVerdict.SATISFIED, MatchVerdict.GAP]
    assert match_posting(kb, 999) is None


def test_storing_matches_replaces_the_previous_run_and_keeps_support(
    kb: sa.Engine, propose: Propose
) -> None:
    rust = _used(kb, propose, "Rust")
    posting = _posting(kb, "Rust", "Fortran")
    results = match_posting(kb, posting)
    assert results is not None

    replace_matches(kb, posting, results)
    replace_matches(kb, posting, results)

    stored = list_matches(kb, posting)
    assert [(m.verdict, m.support) for m in stored] == [
        (MatchVerdict.SATISFIED, (rust,)),
        (MatchVerdict.GAP, ()),
    ]
    assert list_matches(kb, 999) == []


def test_a_verdict_outside_the_closed_set_is_rejected(kb: sa.Engine) -> None:
    from cvforge.kb import schema

    posting = _posting(kb, "Rust")
    with pytest.raises(sa.exc.IntegrityError), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.match).values(
                job_posting_id=posting,
                requirement_id=1,
                verdict="maybe",
                rationale="x",
                computed_at=sa.func.now(),
            )
        )


@pytest.mark.parametrize(
    ("verdict", "support"),
    [
        (MatchVerdict.SATISFIED, ()),
        (MatchVerdict.EVIDENCED, ()),
        (MatchVerdict.UNDOCUMENTED, (1,)),
        (MatchVerdict.GAP, (1,)),
    ],
)
def test_an_outcome_cannot_cite_support_it_should_not_or_omit_support_it_needs(
    verdict: MatchVerdict, support: tuple[int, ...]
) -> None:
    from cvforge.match.verdicts import Outcome

    with pytest.raises(ValueError, match="support"):
        Outcome(verdict, None, "x", support)
