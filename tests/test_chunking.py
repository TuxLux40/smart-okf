"""Tests for the document chunking guard."""

import pytest

from app.services.chunking import chunk_text


def test_text_under_threshold_returns_unchanged_single_chunk() -> None:
    text = "Short document."
    assert chunk_text(text, threshold=1000) == [text]


def test_text_under_threshold_never_imports_chonkie(monkeypatch: pytest.MonkeyPatch) -> None:
    """Common case (most documents) must stay a zero-cost pass-through."""
    import builtins

    real_import = builtins.__import__

    def _guard(name: str, *args: object, **kwargs: object) -> object:
        if name == "chonkie" or name.startswith("chonkie."):
            raise AssertionError("chonkie must not be imported for text under the threshold")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _guard)
    assert chunk_text("short", threshold=1000) == ["short"]


def test_text_over_threshold_splits_into_multiple_chunks_within_budget() -> None:
    text = "This is a sentence. " * 100  # 2000 chars

    chunks = chunk_text(text, threshold=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 250 for chunk in chunks)  # some slack for boundary rules
    assert "".join(chunks) == text  # lossless: no content dropped or duplicated
