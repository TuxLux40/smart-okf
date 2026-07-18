"""Tests for the document chunking guard."""

from app.services.chunking import chunk_text


def test_text_under_threshold_returns_unchanged_single_chunk() -> None:
    text = "Short document."
    assert chunk_text(text, threshold=1000) == [text]


def test_text_over_threshold_splits_into_multiple_chunks_within_budget() -> None:
    text = "This is a sentence. " * 100  # 2000 chars

    chunks = chunk_text(text, threshold=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "".join(chunks) == text  # lossless: no content dropped or duplicated


def test_prefers_paragraph_boundaries() -> None:
    part_a = "A" * 80
    part_b = "B" * 80
    text = f"{part_a}\n\n{part_b}"

    chunks = chunk_text(text, threshold=100)

    assert len(chunks) == 2
    assert chunks[0] == f"{part_a}\n\n"
    assert chunks[1] == part_b
