"""Text extraction helpers for ingest pipeline.

Scanned PDFs (no text layer) are OCRed **in place** with OCRmyPDF before extraction:
the text layer is embedded into the original PDF (searchable/editable ever after) and
never needs re-running — post-OCR the PDF has text, so the OCR branch is skipped on
later ingests.
"""

import os
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


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from a supported document."""
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_DOCUMENT_SUFFIXES:
        raise DocumentIngestError(f"Image OCR not yet implemented for {file_path} (planned: PR 3a/3b)")
    if suffix == ".pdf":
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
