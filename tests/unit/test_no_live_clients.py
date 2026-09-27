"""NFR-08 criterion 2: no test imports a live provider client.

A static check, not a runtime one: `models.ALLOW_MODEL_REQUESTS = False` stops a
live call from *succeeding*, but this stops one from being *attempted* at all —
the two checks cover different failure modes (a bug in the guard fixture itself
would still be caught here).
"""

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
LIVE = {"anthropic", "openai", "ollama"}


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_test_imports_a_live_provider_client() -> None:
    offenders = []
    for path in TESTS.rglob("*.py"):
        if path == Path(__file__):
            continue
        hit = _imported_roots(path.read_text(encoding="utf-8")) & LIVE
        offenders += [f"{path.relative_to(TESTS)} imports {name}" for name in sorted(hit)]
    assert offenders == [], (
        "a test imports a live provider's own client; use TestModel/FunctionModel or a fake "
        f"instead (NFR-08): {offenders}"
    )
