"""Locators are computed by the server from a quoted excerpt, never trusted from a model (FR-15)."""

import pytest

from cvforge.ingest.chunking import Chunk, chunk_pages
from cvforge.ingest.locators import Span, format_locator, resolve_excerpt

PAGE = "Backend engineer at Acme Logistics.\nBuilt a log parser in Rust.\n\nSkills: Python, SQL."


def test_an_exact_excerpt_resolves_to_a_span_that_reproduces_it() -> None:
    span = resolve_excerpt((PAGE,), page=1, excerpt="Built a log parser in Rust.")

    assert span is not None
    assert PAGE[span.start : span.end] == "Built a log parser in Rust."
    assert span.page == 1


def test_whitespace_differences_still_resolve_to_the_original_text() -> None:
    span = resolve_excerpt((PAGE,), page=1, excerpt="Backend  engineer\nat Acme   Logistics.")

    assert span is not None
    assert PAGE[span.start : span.end] == "Backend engineer at Acme Logistics."


def test_case_differences_do_not_resolve() -> None:
    assert resolve_excerpt((PAGE,), page=1, excerpt="built a LOG parser") is None


@pytest.mark.parametrize("excerpt", ["", "   ", "Kubernetes at Globex"])
def test_a_blank_or_absent_excerpt_has_no_locator(excerpt: str) -> None:
    assert resolve_excerpt((PAGE,), page=1, excerpt=excerpt) is None


@pytest.mark.parametrize("page", [0, 3, -1])
def test_a_page_that_does_not_exist_has_no_locator(page: int) -> None:
    assert resolve_excerpt((PAGE, "other"), page=page, excerpt="Rust") is None


def test_the_page_number_selects_the_page_text() -> None:
    span = resolve_excerpt(("alpha", "beta gamma"), page=2, excerpt="gamma")

    assert span == Span(page=2, start=5, end=10)


def test_a_hint_prefers_the_occurrence_nearest_after_it() -> None:
    text = "Rust here. Rust there."

    span = resolve_excerpt((text,), page=1, excerpt="Rust", hint=5)

    assert span is not None and span.start == 11


def test_the_locator_format_is_the_documented_one() -> None:
    assert format_locator(Span(page=2, start=10, end=80)) == "page:2 chars:10-80"


def test_re_resolving_gives_the_same_locator() -> None:
    first = resolve_excerpt((PAGE,), page=1, excerpt="Python, SQL")
    second = resolve_excerpt((PAGE,), page=1, excerpt="Python, SQL")

    assert first == second


def test_a_short_page_is_one_chunk() -> None:
    assert chunk_pages(("short page",), max_chars=100) == [
        Chunk(page=1, offset=0, text="short page")
    ]


def test_a_long_page_splits_on_paragraphs_with_correct_offsets() -> None:
    page = "aaaa\n\nbbbb\n\ncccc"

    chunks = chunk_pages((page,), max_chars=10)

    assert [c.text for c in chunks] == ["aaaa\n\nbbbb", "cccc"]
    for chunk in chunks:
        assert page[chunk.offset : chunk.offset + len(chunk.text)] == chunk.text


def test_one_paragraph_longer_than_the_limit_is_cut_at_the_limit() -> None:
    chunks = chunk_pages(("x" * 25,), max_chars=10)

    assert [len(c.text) for c in chunks] == [10, 10, 5]
    assert [c.offset for c in chunks] == [0, 10, 20]


def test_pages_are_numbered_from_one_and_blank_pages_are_skipped() -> None:
    chunks = chunk_pages(("first", "   ", "third"), max_chars=100)

    assert [(c.page, c.text) for c in chunks] == [(1, "first"), (3, "third")]
