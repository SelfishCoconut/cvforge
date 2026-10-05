"""Keep the requirement issues in step with the SRS (issue #50).

`docs/requirements/srs.md` is the authority on requirements; each requirement issue
carries a *copy* of its SRS block. This tool regenerates every body from the SRS so an
SRS edit cannot silently leave the public tracker asserting the old text.

    uv run python scripts/sync_issues.py --check   # exit 1 on drift, naming the IDs
    uv run python scripts/sync_issues.py           # rewrite only the drifted issues

All bodies are generated and validated before any issue is written, so a malformed
block aborts the whole run. Requirements that trace only to issue #1 (the milestone
epic) have no issue of their own and are not synced. When a ``Traces to`` line lists
several issues ("issues #12 and #48"), only the first is the requirement's copy; the
rest are decision or tracking threads with content of their own and are never touched.

Exit codes: 0 in sync (or synced), 1 drift found by ``--check``, 2 the SRS is malformed
or names an issue the tracker does not have.
"""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SRS_PATH = Path("docs/requirements/srs.md")
DESIGN_SPEC = "docs/superpowers/specs/2026-09-12-cvforge-design.md"
EPIC_ISSUE = 1

_HEADING = re.compile(r"^### ((?:FR|NFR)-\d+) — .+$")
_TRACES = re.compile(r"^- \*\*Traces to\*\*: (.*)$")
_ISSUE_PREFIX = re.compile(r"^issues? (#\d+(?:(?:, | and )#\d+)*), ")


class SrsError(Exception):
    """The SRS cannot be turned into issue bodies, or names an unknown issue."""


@dataclass(frozen=True)
class Requirement:
    """One requirement and the issue body generated from it.

    Attributes:
        req_id: The requirement ID, e.g. ``FR-13``.
        issue: The issue carrying this requirement (the first one its trace lists).
        body: The exact issue body, with no trailing newline.
    """

    req_id: str
    issue: int
    body: str


@dataclass(frozen=True)
class Drift:
    """An issue whose body differs from the SRS.

    Attributes:
        req_id: The requirement ID.
        issue: The drifted issue number.
        expected: The body the SRS calls for.
    """

    req_id: str
    issue: int
    expected: str


def _strip_traces(req_id: str, lines: list[str]) -> tuple[int, list[str]]:
    """Validate the single ``Traces to`` line and remove its issue reference.

    Returns:
        The requirement's issue number and the block lines with the reference stripped.

    Raises:
        SrsError: If the line is missing, duplicated, malformed, or names only an issue.
    """
    found = [i for i, line in enumerate(lines) if _TRACES.match(line)]
    if len(found) != 1:
        raise SrsError(f"{req_id}: expected exactly one 'Traces to' line, found {len(found)}")
    value = lines[found[0]].removeprefix("- **Traces to**: ")
    prefix = _ISSUE_PREFIX.match(value)
    if prefix is None:
        raise SrsError(f"{req_id}: 'Traces to' must start with 'issue #<n>, '")
    issue, *others = (int(n) for n in re.findall(r"\d+", prefix.group(1)))
    rest = value[prefix.end() :].strip()
    if not rest:
        raise SrsError(f"{req_id}: 'Traces to' names only an issue, no test or file")
    if any(f"issue #{n}" in rest for n in (issue, *others)):
        raise SrsError(f"{req_id}: residual 'issue #' reference after stripping")
    lines[found[0]] = f"- **Traces to**: {rest}"
    return issue, lines


def _parse_block(block: str) -> Requirement | None:
    """Turn one SRS section into a `Requirement`, or None if it is not a requirement."""
    lines = block.splitlines()
    heading = _HEADING.match(lines[0]) if lines else None
    if heading is None:
        return None
    req_id = heading.group(1)
    issue, body_lines = _strip_traces(req_id, lines[1:])
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    trailer = f"\n\nSRS entry: `{SRS_PATH}` → {req_id}.\nDesign spec: `{DESIGN_SPEC}`."
    return Requirement(req_id, issue, "\n".join(body_lines) + trailer)


def parse_srs(text: str) -> list[Requirement]:
    """Parse and validate every requirement before anything is written.

    Sections are split just before each level 1-3 heading, so a requirement can never
    swallow the section heading that follows it.

    Args:
        text: The full SRS markdown.

    Returns:
        The syncable requirements, i.e. those not tracing only to the milestone epic.

    Raises:
        SrsError: If any block is malformed, or two requirements share an issue or ID.
    """
    parsed = [r for b in re.split(r"\n(?=#{1,3} )", text) if (r := _parse_block(b))]
    seen_ids: set[str] = set()
    seen_issues: dict[int, str] = {}
    for req in parsed:
        if req.req_id in seen_ids:
            raise SrsError(f"{req.req_id}: defined more than once")
        seen_ids.add(req.req_id)
        if req.issue == EPIC_ISSUE:
            continue
        if req.issue in seen_issues:
            raise SrsError(
                f"issue #{req.issue} claimed by {seen_issues[req.issue]} and {req.req_id}"
            )
        seen_issues[req.issue] = req.req_id
    return [r for r in parsed if r.issue != EPIC_ISSUE]


def find_drift(requirements: Sequence[Requirement], bodies: Mapping[int, str]) -> list[Drift]:
    """Compare the generated bodies with the tracker's.

    A trailing newline is ignored on the tracker side: ``gh issue edit --body-file``
    preserves one, and counting it would report a spurious diff on every run.

    Raises:
        SrsError: If a requirement names an issue absent from ``bodies``.
    """
    drifted: list[Drift] = []
    for req in requirements:
        actual = bodies.get(req.issue)
        if actual is None:
            raise SrsError(f"{req.req_id}: issue #{req.issue} not found in the tracker")
        if actual.rstrip("\n") != req.body:
            drifted.append(Drift(req.req_id, req.issue, req.body))
    return drifted


def gh_fetch_bodies() -> dict[int, str]:
    """Fetch every issue body in one `gh` call."""
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "500", "--json", "number,body"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {int(item["number"]): str(item["body"]) for item in json.loads(out)}


def gh_edit_body(number: int, body: str) -> None:
    """Replace one issue body, passing it on stdin so no trailing newline is added."""
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["gh", "issue", "edit", str(number), "--body-file", "-"],  # noqa: S607
        input=body,
        check=True,
        text=True,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[[], Mapping[int, str]] = gh_fetch_bodies,
    edit: Callable[[int, str], None] = gh_edit_body,
) -> int:
    """Run the sync.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.
        fetch: Returns issue number to body. Injected so tests never touch the network.
        edit: Writes one issue body. Injected for the same reason.

    Returns:
        The process exit code (see the module docstring).
    """
    parser = argparse.ArgumentParser(description="Sync requirement issues from the SRS.")
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    parser.add_argument("--srs", type=Path, default=SRS_PATH, help="path to the SRS")
    args = parser.parse_args(argv)
    try:
        requirements = parse_srs(args.srs.read_text(encoding="utf-8"))
        drifted = find_drift(requirements, fetch())
    except SrsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not drifted:
        print(f"{len(requirements)} requirements in sync")
        return 0
    names = ", ".join(f"{d.req_id} (#{d.issue})" for d in drifted)
    if args.check:
        print(f"drift: {names}", file=sys.stderr)
        return 1
    for item in drifted:
        edit(item.issue, item.expected)
    print(f"updated {len(drifted)} issue bodies: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
