"""PostToolUse warning: a database write appearing outside `kb/apply.py`.

Invariant 2 in CLAUDE.md: `src/cvforge/kb/apply.py` is the only module that
writes entity, edge or assertion rows. The `provenance-auditor` agent and an
invariant test both enforce this; catching it at authoring time is cheaper than
catching it in review.

THE PATTERNS ARE DELIBERATELY BROAD, AND THAT IS NOT AN ACCIDENT. The database
access layer is decided in ADR-0006 (SQLAlchemy Core + Alembic), but the schema
is expected to change repeatedly during M1-M2, and a hook that only recognises
one library's idiom stops working the moment a module reaches for a raw
`sqlite3` cursor -- which is exactly when a stray write is most likely. So this
matches ORM idioms, stdlib `sqlite3` cursors, and raw SQL text alike. A pattern
that silently matches nothing is worse than no check at all, because it reads
as a pass: see `tests/unit/test_hooks.py` for the cases this is held to, and
`tests/integration/test_hooks_wiring.py` for the shell wrapper end to end.

Like the private-data guard, this fails OPEN. It runs after every Edit and
Write in the repository and must never be able to error a tool call.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

WRITES = re.compile(
    # SQLAlchemy ORM / Session idioms.
    r"\.(add|add_all|merge)\("
    # SQLAlchemy Core: session.execute(insert(...)) and friends.
    r"|\.execute\(\s*(insert|update|delete)\("
    # stdlib sqlite3: cursor/conn/connection .execute|.executemany carrying DML.
    r"|\b(cursor|cur|conn|connection|session)\.(execute|executemany)\([^)]*"
    r"\b(INSERT|UPDATE|DELETE)\b"
    # Raw SQL text anywhere.
    r"|\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
    re.IGNORECASE,
)

MESSAGE = (
    "WARNING -- possible database write in {path} ({lines}). Invariant 2: "
    "src/cvforge/kb/apply.py is the ONLY module that may write entity, edge or "
    "assertion rows. If this writes a non-knowledge table (proposals, jobs, CVs, "
    "settings) it may be fine -- say so explicitly in the PR. Otherwise move it "
    "into apply.py. See the kb-schema skill and ADR-0006."
)


def _hits(source: str) -> list[int]:
    return [n for n, line in enumerate(source.splitlines(), 1) if WRITES.search(line)]


def main() -> int:
    """Read the hook payload on stdin and warn if the edited file writes rows."""
    try:
        payload = json.load(sys.stdin)
        path = str((payload.get("tool_input") or {}).get("file_path", "") or "")

        if not path.endswith(".py") or "src/cvforge/" not in path:
            return 0
        if path.endswith("src/cvforge/kb/apply.py"):
            return 0

        hits = _hits(pathlib.Path(path).read_text(encoding="utf-8"))
        if hits:
            lines = ", ".join(f"line {n}" for n in hits[:5])
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": MESSAGE.format(path=path, lines=lines),
                        }
                    }
                )
            )
    except Exception:  # noqa: S110 - failing open is the point; see the module docstring.
        # Not logged: stdout is the hook protocol.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
