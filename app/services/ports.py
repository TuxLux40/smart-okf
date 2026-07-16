"""Structural protocols for service boundaries."""

from typing import Protocol, runtime_checkable

from app.types import RelativePath


@runtime_checkable
class ReviewQueuePort(Protocol):
    """Human review queue for low-confidence ingest or reasoning outputs."""

    def add_item(self, source_path: RelativePath, reason: str) -> None:
        """Enqueue a document for human review."""
        ...
