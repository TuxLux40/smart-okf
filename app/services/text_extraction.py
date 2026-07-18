"""Text extraction helpers for ingest pipeline.

Scanned PDFs (no text layer) are OCRed **in place** with OCRmyPDF before extraction:
the text layer is embedded into the original PDF (searchable/editable ever after) and
never needs re-running — post-OCR the PDF has text, so the OCR branch is skipped on
later ingests. Standalone images are OCRed read-only via tesseract (images have no
embeddable text layer, so their text lives only in the transcript/aggregate).

PDF extraction has an optional `marker` backend (layout-aware: tables, forms, complex
documents) invoked as an external CLI subprocess — never a pip dependency of this
project. marker's code is GPL-3.0 and its model weights use a modified OpenRAIL-M
license; shelling out to a separately-installed `marker_single` binary (same pattern as
`tesseract`/`ocrmypdf`'s `ghostscript` dependency) keeps this MIT-licensed project's own
dependency graph and license unaffected. See README.md for install/licensing notes.
"""

import os
import shutil
import subprocess
import tempfile
from email import message_from_bytes
from email.message import Message
from pathlib import Path

import openpyxl
import pdfplumber
from docx import Document as DocxDocument

from app.constants import IMAGE_DOCUMENT_SUFFIXES, OCR_LANGUAGES, SUPPORTED_DOCUMENT_SUFFIXES, TEXT_FILE_ENCODING
from app.exceptions import DocumentIngestError


def is_supported_document(file_path: Path) -> bool:
    """Return whether a file suffix is supported for ingest."""
    return file_path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES


def extract_text_from_file(file_path: Path, *, use_marker: bool = False) -> str:
    """Extract text from a supported document.

    `use_marker=True` routes `.pdf` extraction through the optional marker CLI backend
    for layout-aware extraction (tables, forms) instead of the default pdfplumber/OCRmyPDF
    pipeline. Explicit-fail if requested but `marker_single` isn't installed, rather than
    silently falling back — a user who opted in should know if they didn't get it.
    """
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_DOCUMENT_SUFFIXES:
        return _extract_text_from_image(file_path)
    if suffix == ".pdf":
        if use_marker:
            if not _marker_available():
                raise DocumentIngestError("marker_single not found on PATH; install marker-pdf or drop --use-marker")
            return _extract_text_from_pdf_via_marker(file_path)
        return _extract_text_from_pdf(file_path)
    if suffix == ".docx":
        return _extract_text_from_docx(file_path)
    if suffix == ".eml":
        return _extract_text_from_eml(file_path)
    if suffix == ".xlsx":
        return _extract_text_from_xlsx(file_path)
    return file_path.read_text(encoding=TEXT_FILE_ENCODING, errors="ignore")


def _extract_text_from_pdf(file_path: Path) -> str:
    """Extract plain text from a PDF; OCR scanned PDFs in place first."""
    text = _read_pdf_text(file_path)
    if text.strip():
        return text
    ocr_pdf_in_place(file_path)
    return _read_pdf_text(file_path)


def _read_pdf_text(file_path: Path) -> str:
    """Extract the existing text layer from a PDF using pdfplumber."""
    pages: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                pages.append(page_text)
    return "\n".join(pages)


def ocr_pdf_in_place(file_path: Path) -> None:
    """Embed an OCR text layer into a scanned PDF, replacing the original atomically.

    Uses OCRmyPDF with `--skip-text` so pages that already carry text are untouched.
    The embedded layer persists in the PDF itself — later ingests and PDF editors get
    the text for free.
    """
    import ocrmypdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", dir=file_path.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        ocrmypdf.ocr(
            file_path,
            temp_path,
            language=OCR_LANGUAGES,
            skip_text=True,
            progress_bar=False,
        )
        os.replace(temp_path, file_path)
    except Exception as error:
        temp_path.unlink(missing_ok=True)
        raise DocumentIngestError(f"OCR failed for {file_path}") from error


def _marker_available() -> bool:
    """Whether a separately-installed `marker_single` binary is on PATH."""
    return shutil.which("marker_single") is not None


def _extract_text_from_pdf_via_marker(file_path: Path) -> str:
    """Shell out to a user-installed `marker_single` CLI for layout-aware PDF extraction."""
    with tempfile.TemporaryDirectory() as out_dir:
        try:
            subprocess.run(
                ["marker_single", str(file_path), "--output_dir", out_dir, "--output_format", "markdown"],
                capture_output=True,
                text=True,
                check=True,
                timeout=600,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise DocumentIngestError(f"marker extraction failed for {file_path}") from error
        produced = next(Path(out_dir).rglob("*.md"), None)
        if produced is None:
            raise DocumentIngestError(f"marker produced no output for {file_path}")
        return produced.read_text(encoding="utf-8")


def _extract_text_from_image(file_path: Path) -> str:
    """OCR a standalone image via tesseract (read-only; the image is not modified)."""
    try:
        completed = subprocess.run(
            ["tesseract", str(file_path), "stdout", "-l", OCR_LANGUAGES],
            capture_output=True,
            text=True,
            errors="replace",
            check=True,
            timeout=300,
        )
    except FileNotFoundError as error:
        raise DocumentIngestError(f"tesseract not installed; cannot OCR {file_path}") from error
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise DocumentIngestError(f"OCR failed for {file_path}") from error
    return completed.stdout


def _extract_text_from_docx(file_path: Path) -> str:
    """Extract paragraph and table text from a .docx file."""
    document = DocxDocument(str(file_path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text for cell in row.cells)
            if row_text.strip():
                parts.append(row_text)
    return "\n".join(parts)


def _extract_text_from_eml(file_path: Path) -> str:
    """Extract headers + plain-text body from a .eml email file."""
    raw = file_path.read_bytes()
    message = message_from_bytes(raw)
    header_lines = [f"{header}: {message.get(header, '')}" for header in ("From", "To", "Subject", "Date")]
    body = _extract_eml_body(message)
    return "\n".join(header_lines) + "\n\n" + body


def _extract_eml_body(message: Message) -> str:
    """Return the first plain-text part of an email message."""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return ""
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(message.get_content_charset() or "utf-8", errors="ignore")
    return str(message.get_payload())


def _extract_text_from_xlsx(file_path: Path) -> str:
    """Extract cell text from all sheets in an .xlsx workbook."""
    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    lines: list[str] = []
    for sheet in workbook.worksheets:
        lines.append(f"# Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            row_text = " | ".join(str(cell) for cell in row if cell is not None)
            if row_text.strip():
                lines.append(row_text)
    return "\n".join(lines)
