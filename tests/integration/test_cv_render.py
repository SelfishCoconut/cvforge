"""FR-26: a CV compiles with the real LaTeX toolchain, and a bad document fails loudly."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.profile import build_profile, matched_posting

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.cv.compile import CompileError, compile_pdf
from cvforge.cv.generate import generate_cv
from cvforge.cv.render import render_tex
from cvforge.cv.store import get_cv, save_cv

pytestmark = pytest.mark.integration


def test_a_generated_cv_compiles_to_a_non_empty_pdf(
    kb: sa.Engine, propose: Any, tmp_path: Path
) -> None:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    cv = get_cv(kb, save_cv(kb, posting, generate_cv(kb, posting)))
    assert cv is not None
    tex = tmp_path / "cv.tex"
    tex.write_text(render_tex(cv), encoding="utf-8")

    pdf = compile_pdf(tex)

    assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 1000


def test_invalid_latex_raises_instead_of_leaving_a_pdf(tmp_path: Path) -> None:
    tex = tmp_path / "bad.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\undefinedmacro\end{document}")
    with pytest.raises(CompileError, match="LaTeX failed"):
        compile_pdf(tex)
    assert not (tmp_path / "bad.pdf").exists() or (tmp_path / "bad.pdf").stat().st_size == 0


@pytest.fixture
def rendering(
    kb: sa.Engine, propose: Any, tmp_path: Path
) -> Iterator[tuple[TestClient, int, Path]]:
    build_profile(kb, propose)
    posting = matched_posting(kb, "Rust")
    out = tmp_path / "cv_out"
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none", cv_out_dir=out)
    with TestClient(create_app(settings, engine=kb), base_url="http://127.0.0.1") as client:
        yield client, posting, out


def test_the_api_writes_all_three_artifacts_under_cv_out(
    rendering: tuple[TestClient, int, Path],
) -> None:
    client, posting, out = rendering
    cv = client.post(f"/api/jobs/{posting}/cvs", json={}).json()

    done = client.post(f"/api/cvs/{cv['id']}/render")

    assert done.status_code == 200
    paths = done.json()
    assert {Path(p).parent for p in paths.values()} == {out / f"cv-{cv['id']}"}
    assert Path(paths["pdf"]).read_bytes().startswith(b"%PDF")
    assert "Rust" in Path(paths["txt"]).read_text() and "Rust" in Path(paths["tex"]).read_text()
    assert client.get(f"/api/cvs/{cv['id']}/files/pdf").headers["content-type"] == "application/pdf"
    assert client.get(f"/api/cvs/{cv['id']}/files/txt").text.startswith("SKILLS")
