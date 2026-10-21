"""FR-17: the Playwright adapter, against a fake `playwright.sync_api` (no browser launched)."""

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import BrowserFetcher, FetchError


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every fixture host resolves to one public address, so no test needs DNS."""
    monkeypatch.setattr("cvforge.web.fetch.resolve_host", lambda host: ["93.184.216.34"])


URL = "https://jobs.example.test/posting/42"


class _FakePlaywrightError(Exception):
    pass


class _Request:
    def __init__(self, url: str) -> None:
        self.url = url


class _Route:
    def __init__(self, url: str) -> None:
        self.request = _Request(url)
        self.outcome = ""

    def abort(self) -> None:
        self.outcome = "abort"

    def continue_(self) -> None:
        self.outcome = "continue"


class _Socket:
    def __init__(self, url: str) -> None:
        self.url = url
        self.outcome = ""

    def close(self) -> None:
        self.outcome = "close"

    def connect_to_server(self) -> None:
        self.outcome = "connect"


class _Page:
    def __init__(self, fail: bool, lands_on: str | None = None) -> None:
        self.fail = fail
        self.lands_on = lands_on
        self.visited: list[str] = []
        self.url = ""
        self.screen: Any = None
        self.screen_socket: Any = None
        self.context_options: dict[str, Any] = {}

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert wait_until == "networkidle"
        if self.fail:
            raise _FakePlaywrightError("net::ERR_NAME_NOT_RESOLVED")
        self.visited.append(url)
        self.url = self.lands_on or url

    def content(self) -> str:
        return "<html>rendered</html>"


class _Browser:
    def __init__(self, page: _Page) -> None:
        self.page = page
        self.closed = False

    def new_context(self, **options: Any) -> "_Browser":
        self.page.context_options = options
        return self

    def route(self, pattern: str, handler: Any) -> None:
        assert pattern == "**/*"
        self.page.screen = handler

    def route_web_socket(self, pattern: str, handler: Any) -> None:
        assert pattern == "**/*"
        self.page.screen_socket = handler

    def new_page(self) -> _Page:
        return self.page

    def close(self) -> None:
        self.closed = True


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, *, fail: bool = False, lands_on: str | None = None
) -> _Browser:
    browser = _Browser(_Page(fail, lands_on))

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


def test_every_request_the_page_makes_is_screened(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = _install_fake(monkeypatch)
    PlaywrightFetcher().render(URL)
    allowed, refused = _Route("https://cdn.example.test/app.js"), _Route("http://10.0.0.1/admin")
    browser.page.screen(allowed)
    browser.page.screen(refused)
    assert (allowed.outcome, refused.outcome) == ("continue", "abort")


def test_a_page_that_ends_on_a_local_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake(monkeypatch, lands_on="http://127.0.0.1:8000/internal")
    with pytest.raises(FetchError, match="local address"):
        PlaywrightFetcher().render(URL)


def test_service_workers_are_blocked_and_websockets_screened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _install_fake(monkeypatch)
    PlaywrightFetcher().render(URL)
    assert browser.page.context_options == {"service_workers": "block"}
    allowed, refused = _Socket("wss://feed.example.test/live"), _Socket("ws://127.0.0.1:9/x")
    browser.page.screen_socket(allowed)
    browser.page.screen_socket(refused)
    assert (allowed.outcome, refused.outcome) == ("connect", "close")
