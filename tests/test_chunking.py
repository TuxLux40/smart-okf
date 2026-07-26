"""Tests for the document chunking guard."""

from app.constants import CHUNK_OVERLAP_CHARS
from app.services.chunking import chunk_text


def test_text_under_threshold_returns_unchanged_single_chunk() -> None:
    text = "Short document."
    assert chunk_text(text, threshold=1000) == [text]


def test_text_over_threshold_splits_into_multiple_chunks_within_budget() -> None:
    text = "This is a sentence. " * 100  # 2000 chars

    chunks = chunk_text(text, threshold=200, overlap=0)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "".join(chunks) == text  # zero-overlap: lossless partition


def test_prefers_paragraph_boundaries() -> None:
    part_a = "A" * 80
    part_b = "B" * 80
    text = f"{part_a}\n\n{part_b}"

    chunks = chunk_text(text, threshold=100, overlap=0)

    assert len(chunks) == 2
    assert chunks[0] == f"{part_a}\n\n"
    assert chunks[1] == part_b


def test_consecutive_chunks_overlap_by_configured_chars() -> None:
    # Uniform text so the splitter takes full-size windows (no soft paragraph break).
    text = "x" * 500

    chunks = chunk_text(text, threshold=200, overlap=50)

    assert len(chunks) > 1
    # Second chunk should start inside the first chunk's tail.
    assert chunks[1][:50] == chunks[0][-50:]
    # Overlap means a naive join is longer than the original (duplicated region).
    assert len("".join(chunks)) > len(text)


def test_fact_on_old_chunk_boundary_appears_whole_in_at_least_one_chunk() -> None:
    # With zero overlap, a fact sitting exactly on the 200-char boundary would be
    # split across chunks. With overlap, at least one chunk must contain it whole.
    left = "A" * 190
    fact = "SECRET_ID_42"
    right = "B" * 200
    text = left + fact + right

    chunks = chunk_text(text, threshold=200, overlap=50)

    assert any(fact in chunk for chunk in chunks)
    # Default production overlap is non-zero.
    assert CHUNK_OVERLAP_CHARS > 0
