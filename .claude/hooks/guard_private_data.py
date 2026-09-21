"""PreToolUse guard: keep personal career data out of a PUBLIC repository.

The previous project deliberately had no such guard. Here it is necessary: the
repository is public and the real knowledge base, uploaded documents and
generated CVs live on the same disk. `.gitignore` covers the normal path; this
blocks the abnormal ones (`git add --force`, an explicit path, a stray write).

This hook gates EVERY Bash, Write and Edit call in this repository, for every
session and every subagent, so two properties matter more than what it detects:

1. It must never raise. A hook that errors is not a denied call, it is a bricked
   repository -- an unterminated `$(` in the shell version of this file once
   blocked all tool use here until it was repaired from outside Claude Code.
   Everything below fails OPEN: anything unexpected exits 0 silently and
   `.gitignore` remains the primary net.
2. It lives in a `.py` file rather than a shell heredoc. The heredoc form it
   replaces (`python3 - <<'PY'`) was silently broken: `python3 -` reads the
   PROGRAM from stdin, so the heredoc *was* stdin, and `json.load(sys.stdin)`
   hit EOF and raised on every single call. The guard denied nothing, ever,
   while exiting 0 and looking exactly like a working guard.
"""

from __future__ import annotations

import json
import re
import sys

# data/ and cv_out/ are two SEPARATE top-level entries in .gitignore (lines 2
# and 6). There is no `data/cv_out/`; saying so in a deny message sends the
# reader to a path that does not exist.
PRIVATE_PATH = re.compile(r"(^|/)(data|cv_out)/|\.db($|[-.])|\.env$")

# `tests/data/` is the ONE place CLAUDE.md sanctions for fixtures, and every
# fixture there is synthetic by rule. Without this exemption PRIVATE_PATH's
# `(^|/)data/` matches it and the guard denies the exact thing it is supposed
# to encourage -- which is how a guard stops being a guard and starts being an
# obstacle people route around.
SANCTIONED = re.compile(r"(^|/)tests/data/")

# A CV-shaped filename anywhere outside the synthetic fixture tree.
CV_SHAPED = re.compile(r"(cv|curriculum|resume)[^/]*\.(pdf|docx?|tex|txt)$", re.IGNORECASE)

# The Bash patterns apply to ONE command segment at a time. Matched against the
# whole line, `git add README.md && rm -f build.log` read as a force-add (the
# `-f` belongs to `rm`), and a guard that cries wolf gets routed around.
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;&|\n]")
GIT_ADD = re.compile(r"\bgit\s+add\b")
FORCE_FLAG = re.compile(r"(^|\s)(-f|--force)(\s|$)")
PRIVATE_IN_CMD = re.compile(r"(^|\s)(\./)?(data|cv_out)/|\.db(\s|$)")


class DenyError(Exception):
    """Raised with the reason to emit; caught by main so nothing escapes."""


def _deny(reason: str) -> None:
    raise DenyError(reason)


def _check_write(path: str) -> None:
    """Raise DenyError if writing `path` would put private data in the repository."""
    if SANCTIONED.search(path):
        return
    if PRIVATE_PATH.search(path):
        _deny(
            f"{path} is private data (data/, cv_out/, *.db, .env). This repository is "
            "PUBLIC. Write it outside the repo, or use tests/data/ with synthetic content."
        )
    if CV_SHAPED.search(path) and "templates/" not in path:
        _deny(
            f"{path} looks like a real CV. Real CVs belong in cv_out/ -- gitignored, and a "
            "separate top-level directory from data/. Only synthetic fixtures under "
            "tests/data/ may be written inside the repo."
        )


def _check_bash(command: str) -> None:
    """Raise DenyError if any segment of `command` stages private data."""
    for segment in SEGMENT_SPLIT.split(" ".join(command.split())):
        if not GIT_ADD.search(segment):
            continue
        if FORCE_FLAG.search(segment):
            _deny(
                "`git add --force` defeats .gitignore, which is the only thing keeping your "
                "knowledge base, documents and generated CVs out of a public repository. "
                "If a file genuinely must be tracked, remove its ignore rule deliberately "
                "in its own commit."
            )
        if PRIVATE_IN_CMD.search(segment):
            _deny(
                "That `git add` names private data (data/, cv_out/ or a database file). "
                "This repository is PUBLIC -- do not track it."
            )


def _check(tool: str, tool_input: dict[str, object]) -> None:
    """Raise DenyError if this call would put private data in the repository."""
    if tool in {"Write", "Edit"}:
        _check_write(str(tool_input.get("file_path", "") or ""))
    elif tool == "Bash":
        _check_bash(str(tool_input.get("command", "") or ""))


def main() -> int:
    """Read the hook payload on stdin and emit a deny decision if warranted."""
    try:
        payload = json.load(sys.stdin)
        _check(str(payload.get("tool_name", "")), payload.get("tool_input") or {})
    except DenyError as denial:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": str(denial),
                    }
                }
            )
        )
    except Exception:  # noqa: S110 - failing open is the point; see the module docstring.
        # Deliberately not logged: stdout IS this hook's protocol, so writing
        # anything but the decision JSON there would corrupt it.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
