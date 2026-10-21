# 0016. Uploaded documents are stored by content hash and parsed to page-separated text

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-14 accepts PDF, DOCX, Markdown and plain text. FR-15 will cite spans of that text
with a page number and a character range, so the text must be stored in a form those
locators can be sliced from later. Uploads are untrusted data (NFR-07).

## Decision

**D-H — parse in process, with no execution of content.** PDF via `pypdf`, DOCX via
`python-docx`, Markdown and plain text decoded as UTF-8. The extension is checked
before any byte is parsed (415); a corrupt or text-less file is a handled 422; the
size cap is 20 MiB (413). Nothing is stored when extraction fails.

**D-I — files are named by the SHA-256 of their bytes**, under
`<data_dir>/documents/`: `<sha>.<ext>` for the original and `<sha>.pages.txt` for the
extracted text, pages separated by a form feed. The uploaded name only supplies the
extension, so a hostile name cannot choose a path, and re-uploading is idempotent. The
paths go on the `source` row (`uri`, `content_hash`, `raw_text_path`), so no schema
change was needed.

**D-J — upload creates a source and nothing else.** It goes through
`apply.record_source`; no entity, edge or proposal exists until FR-15's agent proposes
and Álvaro reviews (invariants 2 and 4). Each upload is a new source even if the bytes
repeat; duplicate *facts* are FR-16's job, not duplicate files.

## Consequences

- Scanned PDFs with no text layer are refused with "no extractable text". OCR is not
  in scope.
- A locator is `page:N chars:a-b` over the page's text as stored in `*.pages.txt`;
  FR-15 must slice from that file, not re-extract, so locators stay stable.
