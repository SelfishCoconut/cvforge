"""Uploading a document stores its bytes privately and extracts its text (FR-14)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.support.documents import docx_bytes, pdf_bytes

from cvforge.app import create_app
from cvforge.config import Settings
from cvforge.ingest.documents import ExtractionError, UnsupportedFormatError, extract_text
from cvforge.kb import queries

PDF = pdf_bytes("Backend engineer at Acme.", "Skills: Python and Rust.")
DOCX = docx_bytes("Backend engineer at Acme.", "Skills: Python and Rust.")
MARKDOWN = b"# Experience\n\nBackend engineer at Acme.\n"
PLAIN = "Ingeniería de backend en Acme.\n".encode()
FORMATS = {
    "cv.pdf": PDF,
    "cv.docx": DOCX,
    "cv.md": MARKDOWN,
    "cv.txt": PLAIN,
}


@pytest.fixture
def docs_client(kb: sa.Engine, tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")
    with TestClient(create_app(settings, engine=kb), base_url="http://127.0.0.1") as client:
        yield client


@pytest.mark.parametrize("name", FORMATS)
def test_each_supported_format_yields_non_empty_text(name: str) -> None:
    document = extract_text(name, FORMATS[name])

    assert document.text.strip()


def test_a_pdf_keeps_its_pages_apart() -> None:
    document = extract_text("cv.pdf", PDF)

    assert len(document.pages) == 2
    assert "Acme" in document.pages[0] and "Rust" in document.pages[1]


def test_plain_text_keeps_non_ascii_characters() -> None:
    assert "Ingeniería" in extract_text("cv.txt", PLAIN).text


def test_an_unsupported_extension_is_refused_before_extraction() -> None:
    with pytest.raises(UnsupportedFormatError, match=r"\.exe"):
        extract_text("setup.exe", b"MZ\x90\x00")


@pytest.mark.parametrize("name", ["cv.pdf", "cv.docx"])
def test_a_corrupt_file_is_a_handled_error(name: str) -> None:
    with pytest.raises(ExtractionError):
        extract_text(name, b"this is not really a document")


def test_undecodable_text_is_a_handled_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text("cv.txt", b"\xff\xfe\x00\x80")


def test_a_document_with_no_text_is_a_handled_error() -> None:
    with pytest.raises(ExtractionError, match="no extractable text"):
        extract_text("cv.md", b"  \n\n ")


def test_an_upload_stores_bytes_under_the_data_dir_and_records_a_source(
    docs_client: TestClient, kb: sa.Engine, tmp_path: Path
) -> None:
    response = docs_client.post("/api/documents", files={"file": ("cv.pdf", PDF)})

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "cv.pdf" and body["pages"] == 2
    stored = list((tmp_path / "data" / "documents").glob("*.pdf"))
    assert len(stored) == 1 and stored[0].read_bytes() == PDF
    with kb.connect() as conn:
        counts = queries.table_counts(conn)
    assert counts["source"] == 1 and counts["entity"] == 0


def test_the_extracted_text_is_kept_page_by_page(docs_client: TestClient, tmp_path: Path) -> None:
    docs_client.post("/api/documents", files={"file": ("cv.pdf", PDF)})

    (text_file,) = (tmp_path / "data" / "documents").glob("*.txt")
    pages = text_file.read_text(encoding="utf-8").split("\f")
    assert len(pages) == 2 and "Rust" in pages[1]


def test_an_unsupported_upload_is_a_415_and_stores_nothing(
    docs_client: TestClient, kb: sa.Engine, tmp_path: Path
) -> None:
    response = docs_client.post("/api/documents", files={"file": ("setup.exe", b"MZ")})

    assert response.status_code == 415 and ".exe" in response.json()["detail"]
    assert not (tmp_path / "data").exists()
    with kb.connect() as conn:
        assert queries.table_counts(conn)["source"] == 0


def test_a_corrupt_upload_is_a_422_and_stores_nothing(
    docs_client: TestClient, kb: sa.Engine, tmp_path: Path
) -> None:
    response = docs_client.post("/api/documents", files={"file": ("cv.pdf", b"garbage")})

    assert response.status_code == 422
    assert not (tmp_path / "data" / "documents").exists()
    with kb.connect() as conn:
        assert queries.table_counts(conn)["source"] == 0


def test_an_oversized_upload_is_a_413(docs_client: TestClient) -> None:
    big = b"a" * (20 * 1024 * 1024 + 1)

    response = docs_client.post("/api/documents", files={"file": ("big.txt", big)})

    assert response.status_code == 413


def test_a_hostile_filename_cannot_choose_the_storage_path(
    docs_client: TestClient, tmp_path: Path
) -> None:
    response = docs_client.post("/api/documents", files={"file": ("../../evil.md", MARKDOWN)})

    assert response.status_code == 201
    (stored,) = (tmp_path / "data" / "documents").glob("*.md")
    assert stored.parent == tmp_path / "data" / "documents"
    assert not (tmp_path / "evil.md").exists()
