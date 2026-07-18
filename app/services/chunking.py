"""Text chunking for documents too large for a single LLM call.

Isolates the chonkie dependency: callers only see `chunk_text()`. Below the threshold,
this never imports or calls chonkie at all — the common case (most documents) stays
exactly as cheap as a direct pass-through.
"""

from app.constants import CHUNK_CHAR_THRESHOLD


def chunk_text(raw_text: str, threshold: int = CHUNK_CHAR_THRESHOLD) -> list[str]:
    """Split raw_text into LLM-sized chunks; returns `[raw_text]` unchanged if under threshold."""
    if len(raw_text) <= threshold:
        return [raw_text]

    from chonkie import RecursiveChunker

    chunker = RecursiveChunker(tokenizer="character", chunk_size=threshold)
    return [chunk.text for chunk in chunker.chunk(raw_text)]
