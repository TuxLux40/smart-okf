#!/usr/bin/env python
"""Generate a static, read-only HTML dashboard: MD browser, git graph, config summary, skill evals.

No server, no daemon — writes one self-contained HTML file. Open it locally, or
serve the single file however you like (`python -m http.server`, Caddy, over
Tailscale/LAN); this script never listens on a socket itself.

Usage:
    uv run python scripts/dashboard.py /path/to/documents
    uv run python scripts/dashboard.py /path/to/documents --output /tmp/dashboard.html
"""

import argparse
import sys
from pathlib import Path

from app.config import load_config
from app.services.dashboard import collect_dashboard_data, render_dashboard

DEFAULT_OUTPUT_NAME = ".okf-dashboard.html"


def main() -> None:
    """CLI entry point for dashboard generation."""
    parser = argparse.ArgumentParser(description="Generate a static, read-only HTML dashboard for a document root.")
    parser.add_argument("folder", help="Document root to build the dashboard for.")
    parser.add_argument(
        "--output",
        default=None,
        help=f"Output HTML path (default: <root>/{DEFAULT_OUTPUT_NAME})",
    )
    args = parser.parse_args()

    root = Path(args.folder).expanduser().resolve()
    config = load_config(root)

    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    data = collect_dashboard_data(root, config)
    output_path = Path(args.output).expanduser().resolve() if args.output else root / DEFAULT_OUTPUT_NAME
    output_path.write_text(render_dashboard(data), encoding="utf-8")
    print(f"Wrote {output_path} ({len(data.entries)} markdown file(s) indexed)")


if __name__ == "__main__":
    main()
