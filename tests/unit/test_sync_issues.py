"""SRS-to-issue sync: parsing, validation, drift detection and the CLI (issue #50)."""

from pathlib import Path

import pytest
from scripts.sync_issues import SRS_PATH, SrsError, find_drift, main, parse_srs

SRS = """# SRS

## Area one

### FR-01 — First
- **Priority**: Must
- **Acceptance criteria**:
  - [x] It works
- **Traces to**: issue #5, tests `tests/unit/test_one.py`

### FR-02 — Second
- **Priority**: Should
- **Traces to**: issues #12 and #48, tests `tests/unit/test_two.py`

## Area two

### NFR-01 — Epic only
- **Traces to**: issue #1, `.github/workflows/ci.yml`; open item tracked in issue #64
"""


def _body(req_id: str, middle: str) -> str:
    return (
        f"{middle}\n\nSRS entry: `docs/requirements/srs.md` → {req_id}.\n"
        "Design spec: `docs/superpowers/specs/2026-09-12-cvforge-design.md`."
    )


FIRST = _body(
    "FR-01",
    "- **Priority**: Must\n- **Acceptance criteria**:\n  - [x] It works\n"
    "- **Traces to**: tests `tests/unit/test_one.py`",
)
SECOND = _body(
    "FR-02",
    "- **Priority**: Should\n- **Traces to**: tests `tests/unit/test_two.py`",
)


def test_bodies_drop_the_heading_and_the_issue_reference_and_gain_a_trailer() -> None:
    first, _second = parse_srs(SRS)

    assert (first.req_id, first.issue, first.body) == ("FR-01", 5, FIRST)
    assert not first.body.endswith("\n")


def test_a_requirement_never_swallows_the_next_section_heading() -> None:
    reqs = parse_srs(SRS)

    assert all("## Area" not in r.body for r in reqs)


def test_only_the_first_listed_issue_is_the_requirements_copy() -> None:
    second = parse_srs(SRS)[1]

    assert (second.issue, second.body) == (12, SECOND)


def test_requirements_tracing_only_to_the_epic_are_not_synced() -> None:
    assert [r.req_id for r in parse_srs(SRS)] == ["FR-01", "FR-02"]


@pytest.mark.parametrize(
    ("traces", "message"),
    [
        ("- **Traces to**: tests `a.py`", "must start with"),
        ("- **Traces to**: issue #5, ", "no test or file"),
        ("- **Traces to**: issue #5, see issue #5 and tests `a.py`", "residual"),
        ("", "found 0"),
        ("- **Traces to**: issue #5, `a.py`\n- **Traces to**: issue #5, `b.py`", "found 2"),
    ],
)
def test_a_malformed_block_is_rejected(traces: str, message: str) -> None:
    with pytest.raises(SrsError, match=message):
        parse_srs(f"### FR-09 — Bad\n- **Priority**: Must\n{traces}\n")


def test_two_requirements_cannot_share_an_issue_or_an_id() -> None:
    block = "### {id} — T\n- **Traces to**: issue #{n}, `a.py`\n\n"

    with pytest.raises(SrsError, match="claimed by FR-01 and FR-02"):
        parse_srs(block.format(id="FR-01", n=5) + block.format(id="FR-02", n=5))
    with pytest.raises(SrsError, match="defined more than once"):
        parse_srs(block.format(id="FR-01", n=5) + block.format(id="FR-01", n=6))


def test_a_synced_tracker_has_no_drift_and_a_trailing_newline_is_not_drift() -> None:
    reqs = parse_srs(SRS)

    assert find_drift(reqs, {5: FIRST, 12: SECOND + "\n"}) == []


def test_an_edited_criterion_is_reported_by_requirement_and_issue() -> None:
    drift = find_drift(parse_srs(SRS), {5: FIRST.replace("[x]", "[ ]"), 12: SECOND})

    assert [(d.req_id, d.issue, d.expected) for d in drift] == [("FR-01", 5, FIRST)]


def test_an_issue_missing_from_the_tracker_is_an_error() -> None:
    with pytest.raises(SrsError, match="issue #12 not found"):
        find_drift(parse_srs(SRS), {5: FIRST})


@pytest.fixture
def srs_file(tmp_path: Path) -> Path:
    path = tmp_path / "srs.md"
    path.write_text(SRS, encoding="utf-8")
    return path


def test_check_exits_zero_when_synced_and_writes_nothing(
    srs_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writes: list[int] = []

    code = main(
        ["--check", "--srs", str(srs_file)],
        fetch=lambda: {5: FIRST, 12: SECOND},
        edit=lambda n, _b: writes.append(n),
    )

    assert (code, writes) == (0, [])
    assert "2 requirements in sync" in capsys.readouterr().out


def test_check_exits_nonzero_naming_the_drifted_ids(
    srs_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writes: list[int] = []

    code = main(
        ["--check", "--srs", str(srs_file)],
        fetch=lambda: {5: "stale", 12: SECOND},
        edit=lambda n, _b: writes.append(n),
    )

    assert (code, writes) == (1, [])
    assert "FR-01 (#5)" in capsys.readouterr().err


def test_sync_rewrites_only_the_drifted_issues(srs_file: Path) -> None:
    written: dict[int, str] = {}

    code = main(
        ["--srs", str(srs_file)],
        fetch=lambda: {5: "stale", 12: SECOND},
        edit=written.__setitem__,
    )

    assert (code, written) == (0, {5: FIRST})


def test_a_malformed_srs_aborts_before_any_issue_is_edited(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "srs.md"
    path.write_text(SRS + "\n### FR-03 — Broken\n- **Priority**: Must\n", encoding="utf-8")
    writes: list[int] = []

    code = main(
        ["--srs", str(path)],
        fetch=lambda: {5: "stale", 12: "stale"},
        edit=lambda n, _b: writes.append(n),
    )

    assert (code, writes) == (2, [])
    assert "FR-03" in capsys.readouterr().err


def test_the_committed_srs_parses_cleanly() -> None:
    reqs = parse_srs(SRS_PATH.read_text(encoding="utf-8"))

    assert len(reqs) > 40
    assert all(r.body and not r.body.endswith("\n") for r in reqs)
