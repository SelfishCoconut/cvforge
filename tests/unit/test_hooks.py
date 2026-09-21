"""The two gating hooks, held to the cases their docstrings promise.

`.claude/hooks/` is not a package, so each hook is loaded from its file path.
Every payload here is synthetic.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("guard_private_data")
kbw = _load("kb_write_path")


def _run_main(
    module: ModuleType,
    stdin: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = module.main()
    return code, capsys.readouterr().out


# --- guard-private-data: Write / Edit ----------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "data/kb.json",
        "/home/u/repo/data/uploads/x.pdf",
        "cv_out/acme.pdf",
        "cvforge.db",
        "cvforge.db-wal",
        "src/.env",
        "notes/my_cv.pdf",
        "Resume-2026.docx",
    ],
)
def test_write_to_private_path_is_denied(path: str) -> None:
    with pytest.raises(guard.DenyError):
        guard._check("Write", {"file_path": path})


@pytest.mark.parametrize(
    "path",
    [
        "src/cvforge/app.py",
        "tests/data/synthetic_cv.pdf",
        "tests/data/kb.db",
        "templates/cv/base.tex",
        "docs/adr/0001-sqlite-knowledge-store.md",
        "",
    ],
)
def test_ordinary_or_sanctioned_write_is_allowed(path: str) -> None:
    guard._check("Edit", {"file_path": path})


def test_write_with_no_file_path_is_allowed() -> None:
    guard._check("Write", {})


# --- guard-private-data: Bash ------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "git add -f data/kb.json",
        "git add --force secrets.txt",
        "git  add   -f  x",
        "git add data/",
        "git add ./cv_out/acme.pdf",
        "git add cvforge.db",
        "cd repo && git add -f notes.md",
    ],
)
def test_force_add_or_staging_private_data_is_denied(cmd: str) -> None:
    with pytest.raises(guard.DenyError):
        guard._check("Bash", {"command": cmd})


@pytest.mark.parametrize(
    "cmd",
    [
        "git status",
        "git add .claude src",
        "git add README.md && rm -f build.log",
        "git add docs; ls -f",
        "git add docs && ls data/",
        "rm -f data.tmp",
        "ls data/",
        "",
    ],
)
def test_ordinary_bash_is_allowed(cmd: str) -> None:
    guard._check("Bash", {"command": cmd})


def test_other_tools_are_ignored() -> None:
    guard._check("Read", {"file_path": "data/kb.json"})


# --- guard-private-data: the hook protocol -----------------------------------


def test_main_emits_a_deny_decision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "data/x"}})
    code, out = _run_main(guard, payload, monkeypatch, capsys)
    assert code == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "data/x" in decision["permissionDecisionReason"]


def test_main_is_silent_when_allowed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert _run_main(guard, payload, monkeypatch, capsys) == (0, "")


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"tool_input": 7}'])
def test_guard_fails_open_on_garbage(
    stdin: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(guard, stdin, monkeypatch, capsys) == (0, "")


# --- kb-write-path -----------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "session.add(entity)",
        "session.add_all(rows)",
        "session.merge(row)",
        "conn.execute(insert(entity_table).values(**v))",
        "conn.execute( update(edge).where(x))",
        "conn.execute(delete(assertion))",
        'cursor.execute("INSERT INTO entity VALUES (?)", v)',
        'cur.executemany("update edge set rel=?", rows)',
        'SQL = "DELETE FROM assertion WHERE id = ?"',
        'q = text("UPDATE entity SET name = :n")',
    ],
)
def test_every_write_idiom_is_flagged(line: str) -> None:
    assert kbw._hits(f"x = 1\n{line}\n") == [2]


@pytest.mark.parametrize(
    "line",
    [
        "conn.execute(select(entity))",
        'cursor.execute("SELECT * FROM entity")',
        "items.append(x)",
        "# we never update anything here",
    ],
)
def test_reads_are_not_flagged(line: str) -> None:
    assert kbw._hits(line) == []


@pytest.mark.parametrize(
    "path",
    ["src/cvforge/kb/apply.py", "tests/unit/test_x.py", "docs/notes.md", "src/cvforge/x.ts"],
)
def test_exempt_or_out_of_scope_paths_are_silent(
    path: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_input": {"file_path": path}})
    assert _run_main(kbw, payload, monkeypatch, capsys) == (0, "")


@pytest.mark.parametrize(
    "stdin", ["", "not json", '{"tool_input": {"file_path": "src/cvforge/nope.py"}}']
)
def test_kb_write_path_fails_open(
    stdin: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(kbw, stdin, monkeypatch, capsys) == (0, "")
