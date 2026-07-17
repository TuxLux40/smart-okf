"""Smoke tests confirming declared runtime dependencies import cleanly."""

import importlib


def test_runtime_dependencies_import() -> None:
    for module_name in ("pydantic", "pydantic_settings", "yaml", "openai", "pdfplumber", "docx", "openpyxl"):
        importlib.import_module(module_name)
