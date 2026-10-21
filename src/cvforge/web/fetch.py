"""Fetch a job posting page by URL and reduce it to plain text (FR-17).

A fetched page is untrusted data (NFR-07). Nothing here interprets it: the HTML is
reduced to text by `trafilatura` and returned, nothing more. Only `http` and `https`
URLs are fetched, every redirect hop is checked again, and unless the caller opts in
a host that is plainly local (`localhost`, a private, loopback or link-local IP
literal) is refused, so a posting link cannot be used to probe the machine or its
network (ADR-0019).

The static path (`httpx` + `trafilatura`) is tried first. A page whose static
extraction is near-empty is probably rendered by JavaScript, so it is handed to a
`BrowserFetcher` (`web/browser.py`) instead. Failure is always a `FetchError`;
empty content is never returned silently.
"""

import ipaddress
from dataclasses import dataclass
from typing import Final, Literal, Protocol, runtime_checkable
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

MAX_RESPONSE_BYTES: Final = 5 * 1024 * 1024
MAX_REDIRECTS: Final = 5
MIN_STATIC_CHARS: Final = 200
TIMEOUT_SECONDS: Final = 15.0
USER_AGENT: Final = "Mozilla/5.0 (compatible; CVForge/0.3; personal job-search tool)"

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    """The page could not be fetched, or held no usable text."""


@runtime_checkable
class BrowserFetcher(Protocol):
    """Renders a page in a real browser and returns its HTML (the JS-board fallback)."""

    def render(self, url: str) -> str:
        """Load `url`, wait for it to settle, and return the rendered HTML.

        Raises:
            FetchError: If the browser is unavailable or the page cannot be loaded.
        """
        ...


@dataclass(frozen=True)
class FetchedPage:
    """The readable text of a fetched page.

    Attributes:
        url: The URL that was requested.
        final_url: Where the static fetch ended up after redirects (equal to `url`
            when the page was rendered by the browser).
        title: The page title, or None if the page declares none.
        text: The extracted main content.
        method: `"static"` or `"browser"`: which path produced `text`.
    """

    url: str
    final_url: str
    title: str | None
    text: str
    method: Literal["static", "browser"]


def _is_local_host(host: str) -> bool:
    """True for `localhost` and for IP literals that are not publicly routable."""
    if host.lower().rstrip(".") == "localhost" or host.lower().endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return not address.is_global


def check_url(url: str, *, allow_local: bool = False) -> None:
    """Refuse a URL that must not be fetched.

    Args:
        url: The candidate URL.
        allow_local: Permit local hosts. Only tests and the offline demo set this.

    Raises:
        FetchError: If the scheme is not http(s), there is no host, or the host is local.
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise FetchError(f"only http and https URLs can be fetched, got {parts.scheme or 'none'!r}")
    if not parts.hostname:
        raise FetchError("the URL has no host")
    if not allow_local and _is_local_host(parts.hostname):
        raise FetchError(f"refusing to fetch a local address: {parts.hostname}")


def _get_html(client: httpx.Client, url: str, *, allow_local: bool) -> tuple[str, str]:
    """GET `url`, following redirects by hand so each hop is checked; return (html, final URL)."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_url(current, allow_local=allow_local)
        try:
            with client.stream("GET", current, headers={"User-Agent": USER_AGENT}) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(f"redirect from {current} without a Location")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise FetchError(f"{current} answered HTTP {response.status_code}")
                body = _read_capped(response)
                return body.decode(response.encoding or "utf-8", errors="replace"), current
        except httpx.HTTPError as exc:
            raise FetchError(f"could not fetch {current}: {exc}") from exc
    raise FetchError(f"more than {MAX_REDIRECTS} redirects from {url}")


def _read_capped(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise FetchError(f"the page is larger than {MAX_RESPONSE_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract(html: str, url: str) -> tuple[str | None, str]:
    """Reduce HTML to (title, main text); the text is empty if nothing readable was found."""
    text = trafilatura.extract(html, url=url, include_tables=True, favor_recall=True) or ""
    metadata = trafilatura.extract_metadata(html, default_url=url)
    return (metadata.title if metadata else None), text.strip()


def fetch_page(
    url: str,
    *,
    client: httpx.Client | None = None,
    browser: BrowserFetcher | None = None,
    allow_local: bool = False,
) -> FetchedPage:
    """Fetch a job posting page and return its readable text.

    Args:
        url: The posting's URL.
        client: The HTTP client; one with sane timeouts is made if omitted.
        browser: The fallback for pages the static path cannot read. Without one, a
            near-empty page is an error.
        allow_local: Permit local hosts (tests and the offline demo only).

    Returns:
        The page text and which path produced it.

    Raises:
        FetchError: If the URL is refused, unreachable or answers an error, or no
            readable text is found even with the browser.
    """
    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        html, final_url = _get_html(http, url, allow_local=allow_local)
    finally:
        if owned:
            http.close()
    title, text = _extract(html, final_url)
    if len(text) >= MIN_STATIC_CHARS:
        return FetchedPage(url, final_url, title, text, "static")
    if browser is None:
        raise FetchError(
            f"{final_url} yielded only {len(text)} characters of text and no browser is available"
        )
    title, text = _extract(browser.render(final_url), final_url)
    if not text:
        raise FetchError(f"{final_url} has no readable text even when rendered in a browser")
    return FetchedPage(url, final_url, title, text, "browser")
