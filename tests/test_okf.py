"""Tests for OKF document models."""

from pathlib import Path

from app.constants import UNKNOWN_OKF_TYPE
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.ingest import apply_ingest_defaults


def test_round_trip_markdown_preserves_frontmatter_and_body() -> None:
    # Arrange
    document = OKFDocument(
        frontmatter=OKFFrontmatter(
            type="Fact",
            title="Birth Date",
            description="Recorded birth date",
            source="records/birth.pdf",
        ),
        body="## Key Facts\n- Born 1901",
    )

    # Act
    parsed = OKFDocument.from_markdown(document.to_markdown())

    # Assert
    assert parsed.frontmatter.type == "Fact"
    assert parsed.frontmatter.title == "Birth Date"
    assert parsed.frontmatter.okf_version is None
    assert "Born 1901" in parsed.body


def test_from_markdown_without_frontmatter_uses_unknown_type() -> None:
    # Arrange
    raw_content = "Plain text without frontmatter."

    # Act
    document = OKFDocument.from_markdown(raw_content)

    # Assert
    assert document.frontmatter.type == UNKNOWN_OKF_TYPE
    assert document.body == raw_content


def test_apply_ingest_defaults_fills_missing_provenance_without_mutation() -> None:
    # Arrange
    root_path = Path("/tmp/docs")
    file_path = root_path / "birth_record.pdf"
    original = OKFDocument(
        frontmatter=OKFFrontmatter.model_validate({"type": "Fact"}),
        body="Body",
    )

    # Act
    updated = apply_ingest_defaults(original, file_path, root_path)

    # Assert
    assert original.frontmatter.source is None
    assert updated.frontmatter.source == "birth_record.pdf"
    assert updated.frontmatter.title == "Birth Record"


def test_from_markdown_with_malformed_yaml_degrades_to_unknown_type() -> None:
    malformed = "---\ntype: Fact\ntitle: Broken: [unclosed\n---\n\nBody text"

    document = OKFDocument.from_markdown(malformed)

    assert document.frontmatter.type == UNKNOWN_OKF_TYPE
    assert "Body text" in document.body
