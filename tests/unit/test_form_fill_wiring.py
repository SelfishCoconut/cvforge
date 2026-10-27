"""FR-37: a headed fill waits for the user, and the default filler uses the private profile."""

from pathlib import Path
from typing import Any

import pytest

from cvforge.api import forms
from cvforge.forms.fill import FillReport, _hold_open


class _Page:
    def __init__(self) -> None:
        self.waited: list[tuple[str, int]] = []

    def wait_for_event(self, event: str, timeout: int) -> None:
        self.waited.append((event, timeout))


@pytest.mark.parametrize(
    ("keep_open", "headless", "waits"),
    [(True, False, True), (True, True, False), (False, False, False)],
)
def test_the_window_is_held_open_only_when_headed_and_asked(
    keep_open: bool, headless: bool, waits: bool
) -> None:
    page = _Page()
    _hold_open(page, keep_open=keep_open, headless=headless)
    assert page.waited == ([("close", 0)] if waits else [])


def test_the_default_filler_uses_the_private_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[Any] = []

    def record(session: Any, profile: Path) -> FillReport:
        seen.append(profile)
        return FillReport((), ())

    monkeypatch.setattr(forms, "fill_session", record)
    forms.make_form_filler(tmp_path)(object())  # type: ignore[arg-type]
    assert seen == [tmp_path / "browser-profile"]
