"""FR-26: LaTeX and plain-text renderings carry the same claims, escaped and deterministic."""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from cvforge.cv.compile import CompileError, compile_pdf
from cvforge.cv.render import latex_escape, render_tex
from cvforge.cv.store import StoredClaim, StoredCv
from cvforge.cv.to_text import render_text
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, CvStatus, GenerationMode


def _cv(*claims: tuple[str, int, ClaimSlot, str]) -> StoredCv:
    stored = tuple(
        StoredClaim(i, section, item, slot, i, ClaimBasis.NAME, text, 1, 1)
        for i, (section, item, slot, text) in enumerate(claims, start=1)
    )
    return StoredCv(
        1,
        1,
        1,
        None,
        None,
        GenerationMode.AUTOMATIC,
        CvStatus.DRAFT,
        datetime(2026, 1, 1),
        None,
        None,
        None,
        stored,
    )


CV = _cv(
    ("Skills", 0, ClaimSlot.BULLET, "C & C++"),
    ("Skills", 0, ClaimSlot.BULLET, "100% uptime_tools"),
    ("Experience", 0, ClaimSlot.HEADER, "Backend Engineer"),
    ("Experience", 0, ClaimSlot.SUBHEADER, "R&D Lab #1"),
    ("Experience", 0, ClaimSlot.PERIOD, "2019-01 to 2022-06"),
    ("Experience", 0, ClaimSlot.BULLET, "Cut costs by $5 {a} ~b ^c \\d"),
)


def test_every_special_character_is_escaped() -> None:
    assert latex_escape("a&b%c$d#e_f{g}h~i^j\\k") == (
        r"a\&b\%c\$d\#e\_f\{g\}h\textasciitilde{}i\textasciicircum{}j\textbackslash{}k"
    )
    assert latex_escape("two\nlines  here") == "two lines here"


def test_the_tex_holds_the_escaped_claims_and_no_raw_specials() -> None:
    tex = render_tex(CV)
    for expected in (r"C \& C++", r"100\% uptime\_tools", r"R\&D Lab \#1", r"2019-01 to 2022-06"):
        assert expected in tex
    assert r"\section*{Skills}" in tex and r"\section*{Experience}" in tex
    assert "%%BODY%%" not in tex


def test_rendering_is_deterministic() -> None:
    assert render_tex(CV) == render_tex(CV)
    assert render_text(CV) == render_text(CV)


def test_the_text_rendering_has_the_same_claims_unescaped() -> None:
    text = render_text(CV)
    assert text.splitlines()[0] == "SKILLS"
    assert "- C & C++" in text and "- 100% uptime_tools" in text
    assert "Backend Engineer - R&D Lab #1 (2019-01 to 2022-06)" in text
    for claim in CV.claims:
        assert claim.text in text


def test_an_empty_cv_renders_without_error() -> None:
    assert render_text(_cv()) == "\n"
    assert r"\begin{document}" in render_tex(_cv())


def test_a_missing_latexmk_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("cvforge.cv.compile.shutil.which", lambda _name: None)
    with pytest.raises(CompileError, match="latexmk is not installed"):
        compile_pdf(tmp_path / "cv.tex")


def test_a_timeout_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def hang(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("latexmk", 1)

    monkeypatch.setattr("cvforge.cv.compile.shutil.which", lambda _name: "/bin/latexmk")
    monkeypatch.setattr(subprocess, "run", hang)
    with pytest.raises(CompileError, match="did not finish"):
        compile_pdf(tmp_path / "cv.tex")


def test_a_failed_run_without_a_pdf_reports_the_log_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "cv.log").write_text("one\ntwo\n! Undefined control sequence.\n")
    monkeypatch.setattr("cvforge.cv.compile.shutil.which", lambda _name: "/bin/latexmk")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 12, "", "")
    )
    with pytest.raises(CompileError, match="Undefined control sequence"):
        compile_pdf(tmp_path / "cv.tex")


def test_a_failed_run_without_a_log_reports_its_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("cvforge.cv.compile.shutil.which", lambda _name: "/bin/latexmk")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "boom", "")
    )
    with pytest.raises(CompileError, match="boom"):
        compile_pdf(tmp_path / "cv.tex")
