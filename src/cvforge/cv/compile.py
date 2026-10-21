"""Compile a `.tex` file to PDF with `latexmk` (FR-26).

The only place in the project that shells out to LaTeX. It fails loudly: a non-zero exit, a
missing tool, a timeout or an empty PDF is a `CompileError` carrying the tail of the LaTeX
log, never a corrupt or missing PDF handed back as success.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Final

TIMEOUT_SECONDS: Final = 120
_LOG_TAIL_LINES: Final = 25


class CompileError(Exception):
    """LaTeX could not produce a PDF."""


def compile_pdf(tex: Path) -> Path:
    """Compile `tex` next to itself and return the PDF's path.

    Args:
        tex: A `.tex` file inside its own output directory.

    Returns:
        The path of the non-empty `.pdf`.

    Raises:
        CompileError: If `latexmk` is missing, times out, fails or yields no PDF; the message
            ends with the tail of the LaTeX log.
    """
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        raise CompileError("latexmk is not installed; install a TeX distribution to build PDFs")
    command = [
        latexmk,
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={tex.parent}",
        str(tex),
    ]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell, path made by us
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, cwd=tex.parent
        )
    except subprocess.TimeoutExpired as exc:
        raise CompileError(f"LaTeX did not finish within {TIMEOUT_SECONDS} s") from exc
    pdf = tex.with_suffix(".pdf")
    if result.returncode != 0 or not pdf.exists() or pdf.stat().st_size == 0:
        log = tex.with_suffix(".log")
        text = log.read_text(errors="replace") if log.exists() else result.stdout + result.stderr
        tail = "\n".join(text.splitlines()[-_LOG_TAIL_LINES:])
        raise CompileError(f"LaTeX failed (exit {result.returncode}):\n{tail}")
    return pdf
