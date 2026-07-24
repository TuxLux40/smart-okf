#!/usr/bin/env python
"""Heuristic plausibility check over every OKF aggregate/matter file under a root.

Not a fact-checker — flags the shape a fabricated or generic extraction takes
(empty sources, missing per-document citations, a body too thin for how many
sources it claims to cover) so a human can glance at just the flagged files
instead of spot-checking the whole tree by hand.

Usage:
    uv run python scripts/validate_okf.py /path/to/documents
"""

import sys
from pathlib import Path

from app.services.validation import validate_tree


def main() -> None:
    """CLI entry point for the validation pass."""
    args = sys.argv[1:]
    if not args:
        print("usage: validate_okf.py /path/to/documents", file=sys.stderr)
        sys.exit(1)
        return

    folder = Path(args[0]).expanduser().resolve()
    reports = validate_tree(folder)

    total = 0
    flagged = 0
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
