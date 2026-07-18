"""Shared extraction policy for ingest + text extraction.

Keeps backend flags (marker, future backends) in one place instead of threading
booleans through every ingest signature.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractionOptions:
    """How to turn source files into raw text before LLM structuring.

    `use_marker` — shell out to external `marker_single` for PDFs (default on).
    Not a pip dependency of this project; onboarding installs marker externally.
    Set false for pdfplumber + in-place OCRmyPDF only (CLI: `--no-marker`).

    `allow_ocr_rewrite` — permit OCRmyPDF to embed a text layer into a scanned PDF
    **in place** (rewrites the original file, invalidating its hash). Read-only paths
    (transcript backfill) must disable this: a pass that reports a folder as
    "unchanged" must never mutate its files.
    """

    use_marker: bool = True
    allow_ocr_rewrite: bool = True


# Light path for transcript backfill / cheap re-reads — never cold-starts marker,
# never mutates source files (no in-place OCR).
LIGHT_EXTRACTION = ExtractionOptions(use_marker=False, allow_ocr_rewrite=False)
DEFAULT_EXTRACTION = ExtractionOptions()
