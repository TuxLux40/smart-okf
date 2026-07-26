#!/usr/bin/env python
"""One-shot / cron-friendly folder ingest.

Writes one aggregate OKF markdown file per folder (non-recursive). Incremental: files
whose SHA-256 is unchanged since the last run are not re-sent to the LLM.

Usage:
    uv run python scripts/ingest_folder.py /path/to/documents
    uv run python scripts/ingest_folder.py /path/to/documents --host http://127.0.0.1:1234 --model gemma-4-e4b-it-qat

Config is read from `<folder>/.smart-okf/config.yaml`, or the nearest ancestor's if `folder`
is a subfolder of an already-onboarded root (see SKILL.md's Onboarding section to create one)
— one config per document root, so it travels with the tree (e.g. over a private git remote)
instead of staying behind on the machine that ran ingest.
"""

import argparse
import sys
from pathlib import Path

from app.config import load_config, resolve_document_root
from app.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL, LLM_LOG_FILENAME
from app.exceptions import LLMClientError
from app.services.extraction_options import ExtractionOptions
from app.services.gating import GatingRules
from app.services.ingest import IngestFolderResult, ingest_folder
from app.services.llm_client import LLMClient
from app.services.text_extraction import marker_available


def main() -> None:
    """CLI entry point for folder ingest."""
    parser = argparse.ArgumentParser(description="Ingest a document folder into per-folder OKF aggregates.")
    parser.add_argument(
        "folder",
        help="Document folder to ingest (recurses; one aggregate per subfolder). "
        "Config is read from <folder>/.smart-okf/config.yaml if present.",
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
    parser.add_argument(
        "--verify-host",
        default=None,
        help="OpenAI-compatible server URL for mandatory fact verification (default: "
        "verify_host from config/env, falling back to the extractor's --host).",
    )
    parser.add_argument(
        "--verify-model",
        default=None,
        help="Model for mandatory fact verification of every extraction (default: verify_model "
        "from config/env, falling back to the extractor's --model). Verification always runs; "
        "this only controls which model checks the extractor's output.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress output")
    parser.add_argument(
        "--allow-model-mismatch",
        action="store_true",
        help="Proceed even if the server at --host isn't currently serving the configured "
        "--model (default: abort). LM Studio/Ollama serve whatever is loaded regardless of "
        "what's requested by name, so a stale/swapped model otherwise degrades extraction "
        "silently — not recommended to bypass this outside a deliberate one-off.",
    )
    args = parser.parse_args()

    root = Path(args.folder).expanduser().resolve()
    config = load_config(root)
    if config is None and args.host is None and args.model is None:
        print(
            f"warning: no .smart-okf/config.yaml found at {root} or any parent — "
            f"using built-in defaults ({DEFAULT_LLM_MODEL} @ {DEFAULT_LLM_HOST}). "
            "Run onboarding (SKILL.md) or pass --host/--model.",
            file=sys.stderr,
        )
    folders = [str(root)]

    host: str | None = args.host or (config.llm_host if config is not None else None)
    model: str | None = args.model or (config.llm_model if config is not None else None)
    vision_model: str | None = args.vision_model or (config.vision_model if config is not None else None)
    # Config-declared generation knobs were previously dead (LLMClient always used
    # module defaults). Wire them through so .smart-okf/config.yaml actually steers
    # extraction capacity and sampling. When no config file exists, LLMClient's own
    # defaults apply (same values as SmartOkfConfig's field defaults).
    llm_max_tokens = config.llm_max_tokens if config is not None else None
    llm_temperature = config.llm_temperature if config is not None else None
    # Verify resolution mirrors dream's model/host fallback: CLI flag > verify_* (config/env)
    # > extractor's own resolved host/model. Verification always runs (see extract_document);
    # this only picks which model does the checking.
    verify_host: str | None = args.verify_host or (config.verify_host if config is not None else None) or host
    verify_model: str | None = args.verify_model or (config.verify_model if config is not None else None) or model
    use_marker = not args.no_marker and (config.use_marker if config is not None else True)
    if use_marker and not marker_available():
        parser.error(
            "marker_single not found on PATH but marker extraction is enabled (default). "
            "Install it (pipx install marker-pdf) or pass --no-marker for pdfplumber/OCRmyPDF only."
        )
        return
    options = ExtractionOptions(use_marker=use_marker)
    rules = GatingRules(
        exclude_patterns=list(config.exclude_patterns) if config is not None else [],
        low_priority_patterns=list(config.low_priority_patterns) if config is not None else [],
        priority_patterns=list(config.priority_patterns) if config is not None else [],
    )
    derive_per_file = config.derive_per_file if config is not None else False
    generate_readme = config.generate_readme if config is not None else True

    combined = IngestFolderResult(root=Path(folders[0]))
    for folder in folders:
        log_path = resolve_document_root(Path(folder)) / LLM_LOG_FILENAME
        client = (
            LLMClient(
                model=model,
                host=host,
                log_path=log_path,
                vision_model=vision_model,
                max_tokens=llm_max_tokens,
                temperature=llm_temperature,
            )
            if llm_max_tokens is not None and llm_temperature is not None
            else LLMClient(model=model, host=host, log_path=log_path, vision_model=vision_model)
        )
        verify_client = (
            client
            if verify_model == model and verify_host == host
            else (
                LLMClient(
                    model=verify_model,
                    host=verify_host,
                    log_path=log_path,
                    max_tokens=llm_max_tokens,
                    temperature=llm_temperature,
                )
                if llm_max_tokens is not None and llm_temperature is not None
                else LLMClient(model=verify_model, host=verify_host, log_path=log_path)
            )
        )

        for candidate in {client, verify_client}:
            try:
                candidate.confirm_model_available()
            except LLMClientError as error:
                if args.allow_model_mismatch:
                    print(f"warning: {error}", file=sys.stderr)
                    continue
                print(f"error: {error}", file=sys.stderr)
                sys.exit(1)

        result = ingest_folder(
            folder,
            client=client,
            options=options,
            verbose=not args.quiet,
            verify_client=verify_client,
            rules=rules,
            derive_per_file=derive_per_file,
            generate_readme=generate_readme,
        )
        combined.written_paths.extend(result.written_paths)
        combined.unchanged_dirs.extend(result.unchanged_dirs)
        combined.skipped.extend(result.skipped)
        combined.removed_paths.extend(result.removed_paths)
        combined.flagged.extend(result.flagged)

    if combined.skipped and not args.quiet:
        print(f"\n{len(combined.skipped)} file(s)/folder(s) skipped:")
        for path, reason in combined.skipped:
            print(f"  {path}: {reason}")

    if combined.flagged and not args.quiet:
        print(f"\n{len(combined.flagged)} file(s)/folder(s) flagged (see _Verification: FLAGGED in the written file):")
        for path, reason in combined.flagged:
            print(f"  {path}: {reason}")

    # 1 = bad root(s), 2 = partial (skips/flags) so cron goes red instead of silently green.
    if not all(Path(f).is_dir() for f in folders):
        sys.exit(1)
    sys.exit(2 if (combined.skipped or combined.flagged) else 0)


if __name__ == "__main__":
    main()
