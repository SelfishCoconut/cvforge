"""The hook wrappers, exercised exactly as Claude Code runs them.

The unit tests cover the Python logic. This covers the layer that once broke
silently: a shell wrapper whose stdin never reached the program. Each case pipes
a synthetic payload into the real `.sh` file.
"""

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"


def _hook(name: str, payload: dict[str, object]) -> str:
    result = subprocess.run(  # noqa: S603 - fixed local script, synthetic input
        ["/bin/sh", str(HOOKS / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_guard_wrapper_denies_a_private_write() -> None:
    out = _hook(
        "guard-private-data.sh", {"tool_name": "Write", "tool_input": {"file_path": "data/x"}}
    )
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_guard_wrapper_is_silent_for_ordinary_work() -> None:
    out = _hook("guard-private-data.sh", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert out == ""


def test_kb_write_path_wrapper_warns_on_a_stray_write(tmp_path: Path) -> None:
    module = tmp_path / "src" / "cvforge" / "stray.py"
    module.parent.mkdir(parents=True)
    module.write_text('def f(conn):\n    conn.execute("INSERT INTO entity VALUES (1)")\n')
    out = _hook("kb-write-path.sh", {"tool_input": {"file_path": str(module)}})
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "line 2" in context
    assert "Invariant 2" in context
