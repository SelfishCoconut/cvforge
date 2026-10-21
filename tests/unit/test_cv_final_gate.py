"""Invariant 5: the only route to a `final` CV is `finalize_cv`, which validates first."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "cvforge"
ALLOWED = {"cv/store.py", "cv/validate.py"}


def test_only_the_validator_reaches_the_status_writer() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Name | ast.Attribute)
        } | {
            alias.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        if "_set_status" in names and rel not in ALLOWED:
            offenders.append(rel)
    assert offenders == [], f"{offenders} reach the CV status writer; use finalize_cv"
