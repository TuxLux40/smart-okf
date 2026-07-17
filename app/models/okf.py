"""Pydantic models for OKF (Open Knowledge Format) structured knowledge items.

Based on Google's OKF spec v0.1: markdown files with YAML frontmatter.
Required: type
Recommended: title, description, tags, timestamp, resource/source.
"""

from datetime import datetime

import yaml
from pydantic import BaseModel, Field

from app.constants import (
    DEFAULT_LINK_LABEL,
    RELATED_SECTION_HEADING,
    UNKNOWN_OKF_TYPE,
)


class OKFFrontmatter(BaseModel):
    """Core OKF frontmatter schema. Extensible with extra fields."""

    type: str = Field(
        ...,
        description=("Concept type e.g. Fact, Event, Person, DocumentSummary, Index, Insight, Pattern"),
    )
    title: str | None = None
    description: str | None = Field(
        None,
        description="One-sentence summary for previews, indices, and agent snippets",
    )
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime | None = Field(default_factory=datetime.now)
    source: str | None = Field(
        None,
        description="Relative path or identifier to original document for provenance",
    )
    resource: str | None = None
    okf_version: str | None = None
    """Per OKF spec §11: only meaningful in a bundle-root index.md, not on every concept."""

    model_config = {
        "extra": "allow",
        "populate_by_name": True,
    }

    def to_yaml(self) -> str:
        """Serialize frontmatter fields to a YAML string."""
        data = self.model_dump(exclude_none=True, mode="json")
        return yaml.dump(data, sort_keys=False, allow_unicode=True)


class OKFDocument(BaseModel):
    """Full OKF document: frontmatter plus markdown body."""

    frontmatter: OKFFrontmatter
    body: str = ""

    def to_markdown(self) -> str:
        """Render the document as OKF markdown with YAML frontmatter."""
        frontmatter_yaml = self.frontmatter.to_yaml()
        return f"---\n{frontmatter_yaml}---\n\n{self.body}"

    @classmethod
    def from_markdown(cls, content: str) -> "OKFDocument":
        """Parse OKF markdown into a document model."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_raw = parts[1].strip()
                body = parts[2].strip()
                frontmatter_data = yaml.safe_load(frontmatter_raw) or {}
                frontmatter = OKFFrontmatter(**frontmatter_data)
                return cls(frontmatter=frontmatter, body=body)
        return cls(
            frontmatter=OKFFrontmatter.model_validate({"type": UNKNOWN_OKF_TYPE}),
            body=content,
        )

    def add_link(self, target: str, context: str = "") -> None:
        """Append a related link to the document body."""
        link_label = self.frontmatter.title or DEFAULT_LINK_LABEL
        link_line = f"- [{link_label}]({target}) {context}".strip()
        if RELATED_SECTION_HEADING not in self.body:
            self.body += f"\n\n{RELATED_SECTION_HEADING}\n"
        if link_line not in self.body:
            self.body += f"\n{link_line}"
