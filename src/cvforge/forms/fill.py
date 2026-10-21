"""Fill the confirmed fields of a form in a visible browser, and never submit it (FR-37).

Only fields the user confirmed in the session are written; everything else is left untouched.
The page is untrusted data (NFR-07): before writing a field the page is re-analysed and the
field must still carry the label and type it had when it was suggested, otherwise it is skipped.
This module never clicks, presses a key or submits: the user reviews the filled form and submits
it themself (ADR-0030, D-BA). A test pins that by reading this file's syntax tree.

The browser runs headed by default, in a dedicated persistent profile under `data/`, never the
user's own browser profile. Requests and WebSockets are screened like the job-page fetcher's;
like it, this does not defend against DNS rebinding inside Chromium (a known limit).
Playwright is imported lazily (optional extra `cvforge[browser]`).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from cvforge.forms.analyze import FormField, analyze_form
from cvforge.forms.store import StoredSession
from cvforge.web.fetch import FetchError, check_url

NAVIGATION_TIMEOUT_MS: Final = 30_000
_TRUE: Final = frozenset({"true", "yes", "on", "1"})


@dataclass(frozen=True)
class FillReport:
    """What a fill run did.

    Attributes:
        filled: Keys of the fields that were written.
        skipped: (key, reason) for each confirmed field that was not written.
    """

    filled: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]


def _same_field(live: dict[str, FormField], entry: dict[str, Any]) -> str | None:
    """Why the stored field no longer matches the page, or None if it still does."""
    found = live.get(entry["key"])
    if found is None:
        return "the field is no longer on the page"
    if found.label != entry["label"] or found.type != entry["type"]:
        return "the page changed since the form was analysed"
    return None


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _write(page: Any, field: FormField, value: str) -> None:
    locator = page.locator(field.selector).first
    if field.type == "select":
        locator.select_option(value=value)
    elif field.type == "checkbox":
        locator.set_checked(value.strip().lower() in _TRUE)
    elif field.type == "radio":
        name, choice = (_escape(v) for v in (field.name or "", value))
        page.locator(f'input[type="radio"][name="{name}"][value="{choice}"]').first.set_checked(
            True
        )
    else:
        locator.fill(value)


def _fill_page(page: Any, session: StoredSession) -> FillReport:
    live = {f.key: f for f in analyze_form(page.content())}
    filled: list[str] = []
    skipped: list[tuple[str, str]] = []
    for entry in session.fields:
        if not entry["confirmed"]:
            continue
        key = entry["key"]
        reason = _same_field(live, entry)
        if reason is None and live[key].sensitive:
            reason = "a password is never filled"
        if reason is None and entry["type"] == "radio" and not live[key].name:
            reason = "an unnamed radio group cannot be targeted"
        if reason is not None:
            skipped.append((key, reason))
            continue
        _write(page, live[key], entry["confirmed_value"])
        filled.append(key)
    return FillReport(tuple(filled), tuple(skipped))


def fill_session(
    session: StoredSession,
    profile_dir: Path,
    *,
    headless: bool = False,
    keep_open: bool = True,
    allow_local: bool = False,
) -> FillReport:
    """Open the form, write the confirmed values, and leave the form unsubmitted.

    Args:
        session: The stored session; only its confirmed fields are written.
        profile_dir: The dedicated browser profile directory (under `data/`).
        headless: Run without a window. The default is headed so the fill is visible.
        keep_open: Wait for the user to close the window, so they can review and submit.
        allow_local: Permit local hosts (tests only).

    Returns:
        Which fields were written and which confirmed fields were skipped, and why.

    Raises:
        FetchError: If Playwright is missing, the URL is refused, or the page cannot be loaded.
    """
    check_url(session.url, allow_local=allow_local)
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise FetchError(
            "filling a form needs a browser; install it with "
            "`uv sync --extra browser && uv run playwright install chromium`"
        ) from exc

    def screen(route: Any) -> None:
        try:
            check_url(route.request.url, allow_local=allow_local)
        except FetchError:
            route.abort()
        else:
            route.continue_()

    def screen_socket(socket: Any) -> None:
        try:
            check_url(socket.url.replace("ws", "http", 1), allow_local=allow_local)
        except FetchError:
            socket.close()
        else:
            socket.connect_to_server()

    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir), headless=headless, service_workers="block"
            )
            try:
                context.route("**/*", screen)
                context.route_web_socket("**/*", screen_socket)
                page = context.new_page()
                page.goto(session.url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT_MS)
                check_url(page.url, allow_local=allow_local)
                report = _fill_page(page, session)
                if keep_open and not headless:
                    page.wait_for_event("close", timeout=0)
                return report
            finally:
                context.close()
    except Error as exc:
        raise FetchError(f"the browser could not fill {session.url}: {exc}") from exc
