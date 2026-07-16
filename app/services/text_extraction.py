"""Text extraction helpers for ingest pipeline."""

from pathlib import Path

import pdfplumber

from app.constants import SUPPORTED_DOCUMENT_SUFFIXES, TEXT_FILE_ENCODING


def is_supported_document(file_path: Path) -> bool:
    """Return whether a file suffix is supported for ingest."""
    return file_path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from a supported document. Placeholder OCR pipeline."""
    if file_path.suffix.lower() == ".pdf":
        return _extract_text_from_pdf(file_path)
    return file_path.read_text(encoding=TEXT_FILE_ENCODING, errors="ignore")


def _extract_text_from_pdf(file_path: Path) -> str:
    """Extract plain text from a PDF using pdfplumber."""
    pages: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                pages.append(page_text)
    return "\n".join(pages)
