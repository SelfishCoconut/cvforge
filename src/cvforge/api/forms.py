"""Analyse an application form page (FR-35).

The page is fetched with the same safeguards as a job posting (public http(s) only, size and
time caps, a browser fallback for JavaScript-built forms) and read for structure only.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cvforge.forms.analyze import FormField, analyze_form
from cvforge.web.browser import PlaywrightFetcher
from cvforge.web.fetch import FetchError, fetch_html

router = APIRouter(tags=["forms"])
HtmlFetcher = Callable[[str], str]


def default_html_fetcher(url: str) -> str:
    """Fetch `url`'s HTML statically, rendering in a browser if the page holds no form.

    Args:
        url: The form page URL.

    Returns:
        The HTML.
    """
    return fetch_html(url, browser=PlaywrightFetcher())


def _fetcher(request: Request) -> HtmlFetcher:
    result: HtmlFetcher = request.app.state.form_html_fetcher
    return result


Fetcher = Annotated[HtmlFetcher, Depends(_fetcher)]


class AnalyzeRequest(BaseModel):
    """A form page to analyse.

    Attributes:
        url: The page's http(s) URL.
    """

    url: str = Field(min_length=1, max_length=2048)


class FieldView(BaseModel):
    """One field of a form.

    Attributes:
        key: A stable identifier within the form.
        label: What the page calls it (`Field N` when it gives no label).
        labelled: False when the label is a placeholder.
        type: The inferred type.
        required: Whether the page marks it required.
        name: The `name` attribute, if any.
        options: The choices of a select or radio group.
        sensitive: True for a password field, which is never suggested or filled.
    """

    key: str
    label: str
    labelled: bool
    type: str
    required: bool
    name: str | None
    options: list[str]
    sensitive: bool


def field_view(item: FormField) -> FieldView:
    """Describe a field for a response (the page-specific selector stays server-side).

    Args:
        item: The analysed field.

    Returns:
        The view.
    """
    return FieldView(
        key=item.key,
        label=item.label,
        labelled=item.labelled,
        type=item.type,
        required=item.required,
        name=item.name,
        options=list(item.options),
        sensitive=item.sensitive,
    )


@router.post("/forms/analyze")
def analyze(body: AnalyzeRequest, fetch: Fetcher) -> list[FieldView]:
    """List the fields of the application form at a URL.

    Args:
        body: The page URL.
        fetch: Fetches the page's HTML.

    Returns:
        The fields in document order; empty if the page has no form.

    Raises:
        HTTPException: 422 if the page cannot be fetched or is refused.
    """
    try:
        html = fetch(body.url)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    return [field_view(f) for f in analyze_form(html)]
