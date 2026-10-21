"""Optional company research through a pluggable search provider (FR-19).

Research is opt-in (NFR-01): with no `SearchProvider` configured nothing is searched
and the job analysis proceeds from the posting alone. Search results are untrusted web
text (NFR-07); this module only collects them and never interprets them. A provider
that fails never fails the caller: the failure is recorded on the result.
"""

from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, runtime_checkable

RESULTS_PER_TOPIC: Final = 5
TOPICS: Final = ("products", "technologies", "engineering practices", "culture")


class SearchError(Exception):
    """A provider could not complete a search."""


@dataclass(frozen=True)
class SearchResult:
    """One search hit.

    Attributes:
        title: The result's title.
        url: Where it points.
        snippet: The provider's excerpt of the page.
    """

    title: str
    url: str
    snippet: str


@runtime_checkable
class SearchProvider(Protocol):
    """A web search backend. Implementations are opt-in and never bundled as a default."""

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Search the web.

        Args:
            query: The search text.
            max_results: The most results to return.

        Returns:
            Up to `max_results` hits.

        Raises:
            SearchError: If the search could not be completed.
        """
        ...


@dataclass(frozen=True)
class CompanyResearch:
    """What research found about a hiring company.

    Attributes:
        status: `"skipped"` (no provider), `"ok"`, or `"failed"` (the provider raised).
        company: The company researched.
        topics: Hits per topic (products, technologies, engineering practices, culture).
            Empty unless `status` is `"ok"`.
        error: Why research failed, when `status` is `"failed"`.
    """

    status: Literal["skipped", "ok", "failed"]
    company: str
    topics: dict[str, list[SearchResult]] = field(default_factory=dict)
    error: str | None = None


def research_company(provider: SearchProvider | None, company: str) -> CompanyResearch:
    """Search the web for what a company builds and how it works, if a provider is set.

    Args:
        provider: The search backend, or None to skip research.
        company: The hiring company's name.

    Returns:
        The findings, or a `skipped` / `failed` result. Never raises for a provider fault.
    """
    if provider is None:
        return CompanyResearch("skipped", company)
    topics: dict[str, list[SearchResult]] = {}
    try:
        for topic in TOPICS:
            hits = provider.search(f"{company} {topic}", max_results=RESULTS_PER_TOPIC)
            topics[topic] = hits[:RESULTS_PER_TOPIC]
    except SearchError as exc:
        return CompanyResearch("failed", company, error=str(exc))
    except Exception as exc:
        return CompanyResearch("failed", company, error=f"{type(exc).__name__}: {exc}")
    return CompanyResearch("ok", company, topics)
