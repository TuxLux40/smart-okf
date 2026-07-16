#!/usr/bin/env python
"""Basic one-shot ingest script for testing Phase 0/1.

Scans a folder, performs OCR/extraction via local LLM, writes co-located OKF MDs.
Run with: python scripts/ingest_folder.py /path/to/test/docs
"""

import sys

from app.services.ingest import ingest_folder


def main(folder: str) -> None:
    """CLI entry point for folder ingest."""
    result = ingest_folder(folder, verbose=True)
    sys.exit(result.exit_code)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_folder.py /path/to/documents")
        sys.exit(1)
    main(sys.argv[1])
