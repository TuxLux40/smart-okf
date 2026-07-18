#!/usr/bin/env python
"""One-shot / cron-friendly folder ingest.

Writes one aggregate OKF markdown file per folder (non-recursive). Incremental: files
whose SHA-256 is unchanged since the last run are not re-sent to the LLM.

Usage:
    uv run python scripts/ingest_folder.py /path/to/documents
    uv run python scripts/ingest_folder.py /path/to/documents --host http://127.0.0.1:1234 --model gemma-4-e4b-it-qat
    uv run python scripts/ingest_folder.py   # no path: reads document_roots from smart-okf.yaml
                                              # (see SKILL.md's Onboarding section to create one)
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from app.config import SmartOkfConfig
from app.constants import LLM_LOG_FILENAME
from app.services.extraction_options import ExtractionOptions
from app.services.ingest import IngestFolderResult, ingest_folder
from app.services.llm_client import LLMClient
from app.services.text_extraction import marker_available


def _load_config() -> SmartOkfConfig | None:
    """Load smart-okf.yaml if present and valid; None otherwise (no error to the user).

    No kwargs passed to the constructor: an explicit `document_roots=...` here would
    count as the (highest-priority) init source and silently override whatever the YAML
    file specifies.
    """
    try:
        return SmartOkfConfig()  # type: ignore[call-arg]
    except ValidationError:
        return None


def main() -> None:
    """CLI entry point for folder ingest."""
    parser = argparse.ArgumentParser(description="Ingest a document folder into per-folder OKF aggregates.")
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Document folder to ingest (recurses; one aggregate per subfolder). "
        "Omit to ingest every document_roots entry from smart-okf.yaml.",
    )
    parser.add_argument("--host", default=None, help="OpenAI-compatible server URL (default: config/env)")
    parser.add_argument("--model", default=None, help="Model name (default: config/env)")
    parser.add_argument(
        "--vision-model",
        default=None,
        help="Vision-capable model for standalone image ingest (handwriting + scene "
        "description), served by --host. Default: config/env, or tesseract-only OCR if unset.",
    )
    parser.add_argument(
        "--no-marker",
        action="store_true",
        help="Skip the marker CLI backend for PDF extraction, using plain pdfplumber/OCRmyPDF "
        "instead. marker is used by default (layout-aware: tables, forms); onboarding installs "
        "its marker_single binary as a prerequisite.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress output")
    args = parser.parse_args()

    config = _load_config()

    folders: list[str]
    if args.folder:
        folders = [args.folder]
    elif config is not None:
        folders = [str(root) for root in config.document_roots]
    else:
        parser.error(
            "no folder given and no valid smart-okf.yaml found; "
            "pass a folder path or complete agent onboarding (see SKILL.md#onboarding-first-run)"
        )
        return

    host: str | None = args.host or (config.llm_host if config is not None else None)
    model: str | None = args.model or (config.llm_model if config is not None else None)
    vision_model: str | None = args.vision_model or (config.vision_model if config is not None else None)
    use_marker = not args.no_marker and (config.use_marker if config is not None else True)
    if use_marker and not marker_available():
        parser.error(
            "marker_single not found on PATH but marker extraction is enabled (default). "
            "Install it (pipx install marker-pdf) or pass --no-marker for pdfplumber/OCRmyPDF only."
        )
        return
    options = ExtractionOptions(use_marker=use_marker)

    combined = IngestFolderResult(root=Path(folders[0]))
    for folder in folders:
        client = LLMClient(model=model, host=host, log_path=Path(folder) / LLM_LOG_FILENAME, vision_model=vision_model)
        result = ingest_folder(folder, client=client, options=options, verbose=not args.quiet)
        combined.written_paths.extend(result.written_paths)
        combined.unchanged_dirs.extend(result.unchanged_dirs)
        combined.skipped.extend(result.skipped)
        combined.removed_paths.extend(result.removed_paths)

    if combined.skipped and not args.quiet:
        print(f"\n{len(combined.skipped)} file(s)/folder(s) skipped:")
        for path, reason in combined.skipped:
            print(f"  {path}: {reason}")

    # 1 = bad root(s), 2 = partial (skips) so cron goes red instead of silently green, 0 = clean.
    if not all(Path(f).is_dir() for f in folders):
        sys.exit(1)
    sys.exit(2 if combined.skipped else 0)


if __name__ == "__main__":
    main()
