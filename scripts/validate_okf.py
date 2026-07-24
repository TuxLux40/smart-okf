#!/usr/bin/env python
"""Heuristic plausibility check over every OKF aggregate/matter file under a root.

Not a fact-checker — flags the shape a fabricated or generic extraction takes
(empty sources, missing per-document citations, a body too thin for how many
sources it claims to cover) so a human can glance at just the flagged files
instead of spot-checking the whole tree by hand.

Usage:
    uv run python scripts/validate_okf.py /path/to/documents
    uv run python scripts/validate_okf.py               # reads document_roots from smart-okf.yaml
"""

import sys
from pathlib import Path

from pydantic import ValidationError

from app.config import SmartOkfConfig
from app.services.validation import validate_tree


def _load_config() -> SmartOkfConfig | None:
    """Load smart-okf.yaml if present and valid; None otherwise."""
    try:
        return SmartOkfConfig()  # type: ignore[call-arg]
    except ValidationError:
        return None


def main() -> None:
    """CLI entry point for the validation pass."""
    args = sys.argv[1:]

    folders: list[str]
    if args:
        folders = [args[0]]
    else:
        config = _load_config()
        if config is None:
            print(
                "no folder given and no valid smart-okf.yaml found; "
                "pass a folder path or complete agent onboarding (see SKILL.md#onboarding-first-run)",
                file=sys.stderr,
            )
            sys.exit(1)
            return
        folders = [str(root) for root in config.document_roots]

    total = 0
    flagged = 0
    for folder in folders:
        reports = validate_tree(Path(folder).expanduser().resolve())
        for report in reports:
            total += 1
            if report.passed:
                continue
            flagged += 1
            print(f"\n{report.path}")
            for finding in report.failures:
                print(f"  FAIL: {finding.text}")
                print(f"        {finding.evidence}")

    print(f"\n{total - flagged}/{total} clean, {flagged} flagged for review")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
