"""FR-17: the Playwright adapter, against a fake `playwright.sync_api` (no browser launched)."""

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import BrowserFetcher, FetchError

URL = "https://jobs.example.test/posting/42"


class _FakePlaywrightError(Exception):
    pass


class _Page:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.visited: list[str] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert wait_until == "networkidle"
        if self.fail:
            raise _FakePlaywrightError("net::ERR_NAME_NOT_RESOLVED")
        self.visited.append(url)

    def content(self) -> str:
        return "<html>rendered</html>"


class _Browser:
    def __init__(self, page: _Page) -> None:
        self.page = page
        self.closed = False

    def new_context(self) -> "_Browser":
        return self

    def new_page(self) -> _Page:
        return self.page

    def close(self) -> None:
        self.closed = True


def _install_fake(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> _Browser:
    browser = _Browser(_Page(fail))

    @contextmanager
    def sync_playwright() -> Iterator[Any]:
        yield types.SimpleNamespace(chromium=types.SimpleNamespace(launch=lambda headless: browser))

    module = types.ModuleType("playwright.sync_api")
    module.Error = _FakePlaywrightError  # type: ignore[attr-defined]
    module.sync_playwright = sync_playwright  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    return browser


def test_it_satisfies_the_fetcher_protocol() -> None:
    assert isinstance(PlaywrightFetcher(), BrowserFetcher)


def test_it_returns_the_rendered_html_and_closes_the_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _install_fake(monkeypatch)
    assert PlaywrightFetcher().render(URL) == "<html>rendered</html>"
    assert browser.page.visited == [URL]
    assert browser.closed


def test_a_load_failure_is_a_fetch_error_and_the_browser_still_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _install_fake(monkeypatch, fail=True)
    with pytest.raises(FetchError, match="could not render"):
        PlaywrightFetcher().render(URL)
    assert browser.closed


def test_a_missing_playwright_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(FetchError, match="--extra browser"):
        PlaywrightFetcher().render(URL)


@pytest.mark.parametrize("url", ["http://127.0.0.1/job", "file:///etc/passwd"])
def test_a_refused_url_never_starts_a_browser(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    browser = _install_fake(monkeypatch)
    with pytest.raises(FetchError):
        PlaywrightFetcher().render(url)
    assert browser.page.visited == []
