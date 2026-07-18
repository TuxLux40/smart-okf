"""Text chunking for documents too large for a single LLM call.

Character-budget splits only (no model-specific tokenizer — the pipeline is backend-agnostic).
Below the threshold this is a zero-cost pass-through: returns `[raw_text]` unchanged.
"""

from app.constants import CHUNK_CHAR_THRESHOLD

# Prefer natural boundaries; require at least this fraction of the budget so we don't
# produce a long trail of tiny chunks when a separator is missing near the start.
_MIN_BREAK_FRACTION = 0.25


def chunk_text(raw_text: str, threshold: int = CHUNK_CHAR_THRESHOLD) -> list[str]:
    """Split raw_text into LLM-sized chunks; returns `[raw_text]` unchanged if under threshold.

    Joining chunks with ``"".join(chunks)`` always reconstructs ``raw_text`` exactly.
    """
    if threshold < 1:
        raise ValueError(f"threshold must be >= 1, got {threshold}")
    if len(raw_text) <= threshold:
        return [raw_text]
    return _split_by_char_budget(raw_text, threshold)


def _split_by_char_budget(text: str, size: int) -> list[str]:
    """Greedy window split preferring paragraph, then line, then space boundaries."""
    chunks: list[str] = []
    start = 0
    n = len(text)
    min_break = max(1, int(size * _MIN_BREAK_FRACTION))

    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            break_at = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
            if break_at >= min_break:
                end = start + break_at + 1
        chunks.append(text[start:end])
        start = end

    return chunks
