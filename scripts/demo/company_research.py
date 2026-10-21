"""Demo (FR-19, M3): company research is skipped without a provider and isolated when one fails.

Offline: the provider is a fake, so no search API is called. It exits non-zero if skipping,
a successful search or a failing provider does not behave as designed.
"""

from cvforge.web.search import SearchError, SearchResult, research_company


class _Search:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        if self.fail:
            raise SearchError("quota exhausted")
        return [SearchResult(f"About: {query}", "https://example.test/about", "snippet")]


def main() -> int:
    """Research a company three ways and report each outcome.

    Returns:
        0 when every outcome matched the design, 1 otherwise.
    """
    skipped = research_company(None, "Example Co")
    print(f"1. no provider   -> {skipped.status}")
    found = research_company(_Search(), "Example Co")
    print(f"2. fake provider -> {found.status}, topics {list(found.topics)}")
    failed = research_company(_Search(fail=True), "Example Co")
    print(f"3. failing       -> {failed.status}: {failed.error}")
    ok = (skipped.status, found.status, failed.status) == ("skipped", "ok", "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
