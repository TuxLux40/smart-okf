"""Tests for the self-updating root navigation README."""

from datetime import datetime
from pathlib import Path

from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.navigation import (
    GENERATED_MARKER,
    README_FILENAME,
    build_navigation,
    collect_stats,
    write_navigation,
)

_FIXED_NOW = datetime(2026, 7, 24, 12, 0)


def _write_aggregate(directory: Path, name: str, sources: list[str], body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    document = OKFDocument(
        frontmatter=OKFFrontmatter(
            type="FolderSummary",
            title=name.title(),
            description=f"{name} documents",
            source=None,
            sources=sources,
        ),
        body=body,
    )
    (directory / f"{name}.md").write_text(document.to_markdown(), encoding="utf-8")


def test_collect_stats_counts_documents_and_folders(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers", "providers", ["providers/a.pdf", "providers/b.pdf"], "body")
    _write_aggregate(tmp_path / "finances", "finances", ["finances/c.pdf"], "body")

    stats = collect_stats(tmp_path)

    assert stats.folders == 2
    assert stats.documents == 3
    assert stats.has_synthesis is False


def test_collect_stats_counts_flagged_verifications(tmp_path: Path) -> None:
    _write_aggregate(
        tmp_path / "providers",
        "providers",
        ["providers/a.pdf"],
        "## A\n\n_Source: a.pdf_\n\n_Verification: FLAGGED — made up a number_\n\nbody",
    )
    assert collect_stats(tmp_path).flagged == 1


def test_build_navigation_links_top_level_folders(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers", "providers", ["providers/a.pdf"], "body")

    markdown = build_navigation(tmp_path, now=_FIXED_NOW)

    assert markdown.startswith(GENERATED_MARKER)
    assert "[providers](providers/providers.md)" in markdown
    assert "2026-07-24" in markdown


def test_write_navigation_creates_readme(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers", "providers", ["providers/a.pdf"], "body")

    written = write_navigation(tmp_path, now=_FIXED_NOW)

    assert written == tmp_path / README_FILENAME
    assert (tmp_path / README_FILENAME).read_text(encoding="utf-8").startswith(GENERATED_MARKER)


def test_write_navigation_overwrites_its_own_generated_readme(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers", "providers", ["providers/a.pdf"], "body")
    write_navigation(tmp_path, now=_FIXED_NOW)
    # Second run must overwrite the marker-bearing file, not bail.
    assert write_navigation(tmp_path, now=_FIXED_NOW) == tmp_path / README_FILENAME


def test_write_navigation_never_clobbers_hand_written_readme(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers", "providers", ["providers/a.pdf"], "body")
    hand_written = tmp_path / README_FILENAME
    hand_written.write_text("# My own README\n\nDo not touch.", encoding="utf-8")

    assert write_navigation(tmp_path, now=_FIXED_NOW) is None
    assert hand_written.read_text(encoding="utf-8") == "# My own README\n\nDo not touch."
