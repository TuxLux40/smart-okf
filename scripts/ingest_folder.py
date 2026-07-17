#!/usr/bin/env python
"""One-shot / cron-friendly folder ingest.

Writes one aggregate OKF markdown file per folder (non-recursive). Incremental: files
whose SHA-256 is unchanged since the last run are not re-sent to the LLM.

Usage:
    uv run python scripts/ingest_folder.py /path/to/documents
    uv run python scripts/ingest_folder.py /path/to/documents --host http://127.0.0.1:1234 --model gemma-4-e4b-it-qat
"""

import argparse
import sys

from app.services.ingest import ingest_folder
from app.services.llm_client import LLMClient


def main() -> None:
    """CLI entry point for folder ingest."""
    parser = argparse.ArgumentParser(description="Ingest a document folder into per-folder OKF aggregates.")
    parser.add_argument("folder", help="Document folder to ingest (recurses; one aggregate per subfolder)")
    parser.add_argument("--host", default=None, help="OpenAI-compatible server URL (default: SMART_OKF_LLM_HOST env)")
    parser.add_argument("--model", default=None, help="Model name (default: SMART_OKF_LLM_MODEL env)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress output")
    args = parser.parse_args()

    client_kwargs = {}
    if args.host:
        client_kwargs["host"] = args.host
    if args.model:
        client_kwargs["model"] = args.model
    client = LLMClient(**client_kwargs)

    result = ingest_folder(args.folder, client=client, verbose=not args.quiet)
    if result.skipped and not args.quiet:
        print(f"\n{len(result.skipped)} file(s)/folder(s) skipped:")
        for path, reason in result.skipped:
            print(f"  {path}: {reason}")
    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
