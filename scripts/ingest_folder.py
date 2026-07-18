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
from app.services.ingest import IngestFolderResult, ingest_folder
from app.services.llm_client import LLMClient


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
        "--use-marker",
        action="store_true",
        help="Route PDF extraction through the optional marker CLI backend (layout-aware: "
        "tables, forms). Requires a separately-installed marker_single binary on PATH.",
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
        parser.error("no folder given and no valid smart-okf.yaml found; run scripts/onboard.py first")
        return

    client_kwargs = {}
    if args.host:
        client_kwargs["host"] = args.host
    elif config is not None:
        client_kwargs["host"] = config.llm_host
    if args.model:
        client_kwargs["model"] = args.model
    elif config is not None:
        client_kwargs["model"] = config.llm_model
    client = LLMClient(**client_kwargs)
    use_marker = args.use_marker or (config.use_marker if config is not None else False)

    combined = IngestFolderResult(root=Path(folders[0]))
    for folder in folders:
        result = ingest_folder(folder, client=client, use_marker=use_marker, verbose=not args.quiet)
        combined.written_paths.extend(result.written_paths)
        combined.unchanged_dirs.extend(result.unchanged_dirs)
        combined.skipped.extend(result.skipped)

    if combined.skipped and not args.quiet:
        print(f"\n{len(combined.skipped)} file(s)/folder(s) skipped:")
        for path, reason in combined.skipped:
            print(f"  {path}: {reason}")
    sys.exit(0 if all(Path(f).is_dir() for f in folders) else 1)


if __name__ == "__main__":
    main()
