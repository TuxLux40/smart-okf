"""Pydantic models for OKF (Open Knowledge Format) structured knowledge items.

Based on Google's OKF spec v0.1: markdown files with YAML frontmatter.
Required: type
Recommended: title, description, tags, timestamp, resource/source.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import yaml

class OKFFrontmatter(BaseModel):
    """Core OKF frontmatter schema. Extensible with extra fields."""
    type: str = Field(..., description="Concept type e.g. Fact, Event, Person, DocumentSummary, Index, Insight, Pattern")
    title: Optional[str] = None
    description: Optional[str] = Field(None, description="One-sentence summary for previews, indices, and agent snippets")
    tags: List[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)
    source: Optional[str] = Field(None, description="Relative path or identifier to original document for provenance")
    resource: Optional[str] = None  # Canonical URI if applicable
    okf_version: str = "0.1"

    # Allow arbitrary extra fields while preserving them
    model_config = {
        "extra": "allow",
        "populate_by_name": True,
    }

    def to_yaml(self) -> str:
        data = self.model_dump(exclude_none=True, mode='json')
        # Convert datetime to ISO string if present
        if 'timestamp' in data and data['timestamp']:
            data['timestamp'] = data['timestamp'].isoformat()
        return yaml.dump(data, sort_keys=False, allow_unicode=True)

class OKFDocument(BaseModel):
    """Full OKF document: frontmatter + markdown body."""
    frontmatter: OKFFrontmatter
    body: str = ""

    def to_markdown(self) -> str:
        fm_yaml = self.frontmatter.to_yaml()
        return f"---\n{fm_yaml}---\n\n{self.body}"

    @classmethod
    def from_markdown(cls, content: str) -> "OKFDocument":
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_raw = parts[1].strip()
                body = parts[2].strip()
                fm_data = yaml.safe_load(fm_raw) or {}
                frontmatter = OKFFrontmatter(**fm_data)
                return cls(frontmatter=frontmatter, body=body)
        # Fallback: treat whole as body, minimal frontmatter
        return cls(frontmatter=OKFFrontmatter(type="Unknown"), body=content)

    def add_link(self, target: str, context: str = "") -> None:
        """Helper to add a markdown link section or update body."""
        link_line = f"- [{self.frontmatter.title or 'Related'}]({target}) {context}".strip()
        if "## Related" not in self.body:
            self.body += "\n\n## Related\n"
        if link_line not in self.body:
            self.body += f"\n{link_line}"

# Example usage in other modules:
# doc = OKFDocument(frontmatter=OKFFrontmatter(type="Fact", title="Example", description="..."), body="Details here.")
# print(doc.to_markdown())
