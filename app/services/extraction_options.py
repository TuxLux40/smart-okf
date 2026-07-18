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
    """

    use_marker: bool = True


# Light path for transcript backfill / cheap re-reads — never cold-starts marker.
LIGHT_EXTRACTION = ExtractionOptions(use_marker=False)
DEFAULT_EXTRACTION = ExtractionOptions()
