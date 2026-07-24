#!/usr/bin/env python
"""Cross-folder "dream" synthesis pass — run after (or independently of) ingest.

Reads every folder aggregate under the root and writes one `<root>/synthesis.md`
(`type: Synthesis`): matters spanning folders, conflicts, patterns, open actions.
Incremental: zero LLM calls when no aggregate changed since the last dream.

Usage:
    uv run python scripts/dream.py /path/to/documents
    uv run python scripts/dream.py               # reads document_roots from smart-okf.yaml
    uv run python scripts/dream.py --force       # re-dream even if nothing changed
"""

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from app.config import SmartOkfConfig
from app.constants import LLM_LOG_FILENAME
from app.services.dream import dream
from app.services.gating import GatingRules
from app.services.llm_client import LLMClient


def _load_config() -> SmartOkfConfig | None:
    """Load smart-okf.yaml if present and valid; None otherwise."""
    try:
        return SmartOkfConfig()  # type: ignore[call-arg]
    except ValidationError:
        return None


def main() -> None:
    """CLI entry point for the dream pass."""
    parser = argparse.ArgumentParser(description="Synthesize matters/conflicts/patterns/actions across aggregates.")
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Document root to dream over. Omit to use every document_roots entry from smart-okf.yaml.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="OpenAI-compatible server URL for the dreamer (default: dream_host from config/env, "
        "falling back to the extractor's llm_host)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Dreamer model name (default: dream_model from config/env, falling back to llm_model). "
        "Dreaming is reasoning, not extraction — use the smartest model you have access to.",
    )
    parser.add_argument("--force", action="store_true", help="Re-dream even when no aggregate changed")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
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

    # Dreamer resolution: CLI flag > dream_* (config/env) > extractor settings (config, then
    # LLMClient's own SMART_OKF_LLM_* env fallback via model/host=None).
    host: str | None = (
        args.host
        or os.getenv("SMART_OKF_DREAM_HOST")
        or ((config.dream_host or config.llm_host) if config is not None else None)
    )
    model: str | None = (
        args.model
        or os.getenv("SMART_OKF_DREAM_MODEL")
        or ((config.dream_model or config.llm_model) if config is not None else None)
    )

    rules = GatingRules(
        low_priority_patterns=list(config.low_priority_patterns) if config is not None else [],
        priority_patterns=list(config.priority_patterns) if config is not None else [],
    )
    ordering_principle = config.ordering_principle if config is not None else "provenance"

    exit_code = 0
    for folder in folders:
        client = LLMClient(model=model, host=host, log_path=Path(folder) / LLM_LOG_FILENAME)
        result = dream(
            folder,
            client=client,
            force=args.force,
            verbose=not args.quiet,
            rules=rules,
            ordering_principle=ordering_principle,
        )
        for error in result.errors:
            print(f"Error: {error}", file=sys.stderr)
        exit_code = max(exit_code, result.exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
