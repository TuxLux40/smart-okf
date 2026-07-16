"""Shared type aliases for smart-okf."""

from typing import TypeAlias

RelativePath: TypeAlias = str
"""Path relative to a document root (provenance / source field)."""

MarkdownContent: TypeAlias = str
"""Full OKF markdown document (frontmatter + body)."""

OkfTypeName: TypeAlias = str
"""OKF frontmatter `type` value (Fact, Event, Person, …)."""

FrontmatterPatch: TypeAlias = dict[str, str]
"""String fields to merge into OKF frontmatter via `model_copy`."""
