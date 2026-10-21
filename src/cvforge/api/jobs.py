"""Job intake: fetch a posting, analyse it, optionally research the company, store it (M3).

The posting is untrusted text (NFR-07). It is fetched, handed to a tool-free agent, and
stored as a posting; nothing here creates an entity, an edge or a proposal.
"""

import logging
from collections.abc import Callable
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from cvforge.api.chat import Factory
from cvforge.api.errors import engine
from cvforge.jobs.store import StoredPosting, get_posting, list_postings, persist_posting
from cvforge.kb import apply
from cvforge.kb.vocab import RequirementKind, WorkModel
from cvforge.llm.agents.job import AnalysisError, analyze_posting
from cvforge.llm.schemas import JobAnalysis
from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import FetchedPage, FetchError, fetch_page
from cvforge.web.search import CompanyResearch, SearchProvider, research_company

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])
Engine = Annotated[sa.Engine, Depends(engine)]
JobFetcher = Callable[[str], FetchedPage]


def default_fetcher(url: str) -> FetchedPage:
    """Fetch `url` statically, falling back to a real browser if one is installed.

    Args:
        url: The posting URL.

    Returns:
        The fetched page.
    """
    return fetch_page(url, browser=PlaywrightFetcher())


def _fetcher(request: Request) -> JobFetcher:
    result: JobFetcher = request.app.state.job_fetcher
    return result


def _search_provider(request: Request) -> SearchProvider | None:
    result: SearchProvider | None = request.app.state.search_provider
    return result


Fetcher = Annotated[JobFetcher, Depends(_fetcher)]
Search = Annotated[SearchProvider | None, Depends(_search_provider)]


class JobRequest(BaseModel):
    """A posting to take in.

    Attributes:
        url: The posting's http(s) URL.
    """

    url: str = Field(min_length=1, max_length=2048)


class RequirementView(BaseModel):
    """One requirement of a posting.

    Attributes:
        kind: `required`, `preferred` or `responsibility`.
        text: What the posting asks.
    """

    kind: RequirementKind
    text: str


class ResearchView(BaseModel):
    """What optional company research found.

    Attributes:
        status: `skipped` (no provider), `ok` or `failed`.
        error: Why it failed, when it did.
        topics: Hit titles and URLs per topic.
    """

    status: str
    error: str | None
    topics: dict[str, list[dict[str, str]]]


class JobView(BaseModel):
    """A stored posting.

    Attributes:
        id: The posting id.
        created: True if this call created it, False if it updated the stored one.
        url: The normalised URL the posting is keyed by.
        source_id: The `web` source of the latest fetch.
        title: The job title, if stated.
        seniority: The seniority, if stated.
        location: The location, if stated.
        work_model: Remote, hybrid or on-site, if stated.
        analysis: The structured analysis.
        requirements: The decomposed requirements.
        research: Company research, only on the call that ran it.
    """

    id: int
    created: bool | None = None
    url: str
    source_id: int
    title: str | None
    seniority: str | None
    location: str | None
    work_model: WorkModel | None
    analysis: JobAnalysis
    requirements: list[RequirementView]
    research: ResearchView | None = None


def _view(
    posting: StoredPosting, *, created: bool | None = None, research: CompanyResearch | None = None
) -> JobView:
    return JobView(
        id=posting.id,
        created=created,
        url=posting.url,
        source_id=posting.source_id,
        title=posting.title,
        seniority=posting.seniority,
        location=posting.location,
        work_model=posting.work_model,
        analysis=posting.analysis,
        requirements=[RequirementView(kind=r.kind, text=r.text) for r in posting.requirements],
        research=_research_view(research),
    )


def _research_view(research: CompanyResearch | None) -> ResearchView | None:
    if research is None:
        return None
    return ResearchView(
        status=research.status,
        error=research.error,
        topics={
            topic: [{"title": hit.title, "url": hit.url} for hit in hits]
            for topic, hits in research.topics.items()
        },
    )


def _require(db: sa.Engine, posting_id: int) -> StoredPosting:
    posting = get_posting(db, posting_id)
    if posting is None:
        raise apply.NotFoundError(f"no job posting {posting_id}")
    return posting


@router.post("/jobs")
def take_in_posting(
    body: JobRequest,
    response: Response,
    db: Engine,
    fetcher: Fetcher,
    model_factory: Factory,
    search: Search,
) -> JobView:
    """Fetch a job posting by URL, analyse it, and store it with its requirements.

    Taking in a URL that is already stored updates that posting rather than adding another.
    Company research runs only when a search provider is configured, and its failure never
    fails the request.

    Args:
        body: The posting URL.
        response: The response, whose status is 201 for a new posting and 200 for an update.
        db: The knowledge-base engine.
        fetcher: Fetches the page.
        model_factory: Builds the model for this request.
        search: The optional company-research provider.

    Returns:
        The stored posting.

    Raises:
        HTTPException: 422 if the page cannot be fetched or is refused; 502 if the model
            returns no valid analysis.
    """
    try:
        page = fetcher(body.url)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        analysis = analyze_posting(model_factory(db), page.text)
    except AnalysisError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        logger.warning("job analysis failed: %s", exc)
        raise HTTPException(502, f"the model could not analyse the posting: {exc}") from exc
    research = research_company(search, analysis.company) if search and analysis.company else None
    stored = persist_posting(db, page, analysis, url=body.url)
    response.status_code = 201 if stored.created else 200
    return _view(_require(db, stored.id), created=stored.created, research=research)


@router.get("/jobs")
def list_jobs(db: Engine) -> list[JobView]:
    """List the stored postings, newest first.

    Args:
        db: The knowledge-base engine.

    Returns:
        Every posting with its requirements.
    """
    return [_view(posting) for posting in list_postings(db)]


@router.get("/jobs/{posting_id}")
def read_job(posting_id: int, db: Engine) -> JobView:
    """Read one stored posting.

    Args:
        posting_id: A posting id.
        db: The knowledge-base engine.

    Returns:
        The posting.

    Raises:
        NotFoundError: If there is no such posting (404).
    """
    return _view(_require(db, posting_id))
