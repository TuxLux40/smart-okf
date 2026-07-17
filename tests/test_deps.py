"""Smoke tests confirming declared runtime dependencies import cleanly."""

import importlib


def test_new_pr0_dependencies_import() -> None:
    for module_name in ("pydantic_settings", "structlog", "mcp", "portalocker"):
        importlib.import_module(module_name)
