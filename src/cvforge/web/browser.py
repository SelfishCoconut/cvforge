"""Playwright-backed `BrowserFetcher` for JavaScript-rendered job boards (FR-17).

Playwright is an optional extra (`pip install cvforge[browser]`, then
`playwright install chromium`), so it is imported only when a page is rendered. This
fetcher uses a fresh, throwaway browser context with no stored login: the persistent
profile of M8's form filling is deliberately not used for reading postings.
"""

from typing import Any, Final

from cvforge.web.fetch import FetchError, check_url

NAVIGATION_TIMEOUT_MS: Final = 30_000


class PlaywrightFetcher:
    """Renders a page in headless Chromium and returns the resulting HTML."""

    def __init__(self, *, allow_local: bool = False) -> None:
        """Create the fetcher.

        Args:
            allow_local: Permit local hosts (tests and the offline demo only).
        """
        self._allow_local = allow_local

    def _screen(self, route: Any) -> None:
        """Abort any request, navigation or redirect hop, that `check_url` refuses."""
        try:
            check_url(route.request.url, allow_local=self._allow_local)
        except FetchError:
            route.abort()
        else:
            route.continue_()

    def render(self, url: str) -> str:
        """Load `url` in headless Chromium, wait for the network to settle, return the HTML.

        Args:
            url: The page to render. Checked like any other fetch.

        Returns:
            The page's HTML after scripts ran.

        Raises:
            FetchError: If Playwright is not installed, the URL is refused, or the
                page cannot be loaded.
        """
        check_url(url, allow_local=self._allow_local)
        try:
            from playwright.sync_api import Error, sync_playwright
        except ImportError as exc:
            raise FetchError(
                "this page needs a browser to render; install it with "
                "`uv sync --extra browser && uv run playwright install chromium`"
            ) from exc
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_context().new_page()
                    page.route("**/*", self._screen)
                    page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT_MS)
                    check_url(page.url, allow_local=self._allow_local)
                    html: str = page.content()
                    return html
                finally:
                    browser.close()
        except Error as exc:
            raise FetchError(f"the browser could not render {url}: {exc}") from exc
