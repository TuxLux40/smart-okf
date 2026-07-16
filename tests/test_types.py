"""Tests for type aliases and protocol structural typing."""

from app.services.ports import ReviewQueuePort
from app.types import FrontmatterPatch, RelativePath


class _RecordingReviewQueue:
    def __init__(self) -> None:
        self.items: list[tuple[RelativePath, str]] = []

    def add_item(self, source_path: RelativePath, reason: str) -> None:
        self.items.append((source_path, reason))


def test_review_queue_port_satisfied_by_structural_type() -> None:
    queue = _RecordingReviewQueue()
    assert isinstance(queue, ReviewQueuePort)
    queue.add_item("docs/a.pdf", "low confidence")
    assert queue.items == [("docs/a.pdf", "low confidence")]


def test_frontmatter_patch_alias_accepts_string_fields() -> None:
    patch: FrontmatterPatch = {"source": "a.pdf", "title": "A"}
    assert patch["source"] == "a.pdf"
