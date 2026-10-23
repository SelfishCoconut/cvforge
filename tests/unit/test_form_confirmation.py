"""FR-37: only fields the user confirmed can be filled, and never twice; none is ever submitted."""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.cv.store import save_cv
from cvforge.forms.analyze import FormField
from cvforge.forms.options import Suggestion
from cvforge.forms.store import (
    SessionError,
    confirm_field,
    create_session,
    get_session,
    mark_filled,
    unconfirm_field,
)

FORMS = Path(__file__).resolve().parents[2] / "src" / "cvforge" / "forms"
FIELDS = [
    FormField("f1", "Years", True, "text", False, "y", (), "#y", False),
    FormField("f2", "Level", True, "select", False, "l", ("jr", "sr"), "#l", False),
    FormField("f3", "Secret", True, "password", False, "p", (), "#p", True),
    FormField("f4", "CV", True, "file", False, "c", (), "#c", False),
]


@pytest.fixture
def session(kb: sa.Engine, propose: Any) -> int:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = save_cv(kb, posting, generate_cv(kb, posting))
    suggestions = [Suggestion(f.key, None, (), "manual") for f in FIELDS]
    return create_session(
        kb, cv_id=cv, url="https://x.test/f", fields=FIELDS, suggestions=suggestions
    )


def _fields(kb: sa.Engine, session: int) -> dict[str, dict[str, Any]]:
    stored = get_session(kb, session)
    assert stored is not None
    return {f["key"]: f for f in stored.fields}


def test_confirming_records_the_value_and_unconfirming_withdraws_it(
    kb: sa.Engine, session: int
) -> None:
    confirm_field(kb, session, "f1", "7")
    assert _fields(kb, session)["f1"]["confirmed_value"] == "7"
    assert not _fields(kb, session)["f2"]["confirmed"]
    unconfirm_field(kb, session, "f1")
    assert not _fields(kb, session)["f1"]["confirmed"]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("f9", "x", "no field"),
        ("f1", "  ", "blank"),
        ("f2", "mid", "not an option"),
        ("f3", "hunter2", "never filled"),
        ("f4", "cv.pdf", "never filled"),
    ],
)
def test_a_confirmation_the_field_cannot_take_is_refused(
    kb: sa.Engine, session: int, key: str, value: str, message: str
) -> None:
    with pytest.raises(SessionError, match=message):
        confirm_field(kb, session, key, value)
    assert not any(f["confirmed"] for f in _fields(kb, session).values())


def test_a_filled_session_is_closed_to_changes(kb: sa.Engine, session: int) -> None:
    mark_filled(kb, session)
    calls: list[Callable[[], None]] = [
        lambda: confirm_field(kb, session, "f1", "7"),
        lambda: unconfirm_field(kb, session, "f1"),
        lambda: mark_filled(kb, session),
    ]
    for call in calls:
        with pytest.raises(SessionError, match="already filled"):
            call()


def test_an_unknown_session_or_field_is_refused(kb: sa.Engine, session: int) -> None:
    calls: list[Callable[[], None]] = [
        lambda: confirm_field(kb, 999, "f1", "7"),
        lambda: unconfirm_field(kb, 999, "f1"),
        lambda: unconfirm_field(kb, session, "f9"),
        lambda: mark_filled(kb, 999),
    ]
    for call in calls:
        with pytest.raises(SessionError):
            call()


FORBIDDEN = {
    "click", "dblclick", "tap", "press", "press_sequentially", "type", "submit", "evaluate",
    "evaluate_handle", "dispatch_event", "requestSubmit", "eval_on_selector",
    "add_script_tag", "expose_function", "expose_binding",
}  # fmt: skip


def test_no_forms_code_clicks_presses_or_submits() -> None:
    """The syntax tree of every `forms/` module names no action that could submit a form."""
    offences = [
        f"{path.name}:{node.lineno} {node.func.attr}"
        for path in FORMS.glob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN
    ]
    assert offences == []
