"""A synthetic professional profile, committed through the real pipeline, for CV tests."""

from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from cvforge.jobs.store import persist_posting
from cvforge.kb import apply
from cvforge.llm.schemas import JobAnalysis
from cvforge.match.store import replace_matches
from cvforge.match.verdicts import match_posting
from cvforge.web.fetch import FetchedPage


@dataclass(frozen=True)
class Profile:
    """Entity ids of the synthetic profile."""

    rust: int
    python: int
    haskell: int
    role: int
    org: int
    project: int
    education: int
    credential: int


def _create(kind: str, name: str, **extra: Any) -> dict[str, Any]:
    return {"op_type": "create_entity", "kind": kind, "name": name, **extra}


def build_profile(kb: sa.Engine, propose: Any) -> Profile:
    """Commit a profile: Rust used in a log parser at Acme, plus unused Python, a Haskell gap."""
    ids = apply.commit_proposal(
        kb,
        propose(
            _create("skill", "Rust"),
            _create("skill", "Python"),
            _create("skill", "Haskell", state="gap"),
            _create(
                "role",
                "Backend Engineer",
                summary="Built data services",
                attributes={
                    "started_at": "2019-01-01",
                    "ended_at": "2022-06-30",
                    "employment_type": "full-time",
                },
            ),
            _create("organization", "Acme Logistics"),
            _create("project", "Log parser", summary="Parsed two gigabytes per second"),
            _create(
                "education",
                "BSc Computer Science",
                attributes={"started_at": "2014-09-01", "ended_at": "2018-06-30"},
            ),
            _create(
                "credential", "AWS Certified Developer", attributes={"issued_at": "2021-03-01"}
            ),
            accept=True,
        ),
    ).entity_ids
    rust, python, haskell, role, org, project, education, credential = (ids[i] for i in range(8))

    def edge(src: int, rel: str, dst: int) -> dict[str, Any]:
        return {"op_type": "add_edge", "src": src, "rel": rel, "dst": dst}

    apply.commit_proposal(
        kb,
        propose(
            edge(rust, "used_in", project),
            edge(project, "part_of", role),
            edge(role, "at_organization", org),
            accept=True,
        ),
    )
    return Profile(rust, python, haskell, role, org, project, education, credential)


def matched_posting(kb: sa.Engine, *skills: str) -> int:
    """Persist a posting that requires `skills`, match it, and store the verdicts."""
    page = FetchedPage("https://j.test/1", "https://j.test/1", "J", "t", "static")
    posting = persist_posting(kb, page, JobAnalysis(required_skills=list(skills))).id
    results = match_posting(kb, posting)
    assert results is not None
    replace_matches(kb, posting, results)
    return posting
