"""Tests for per-matter concept files (R2)."""

from pathlib import Path

from app.services.matter_files import (
    group_source_hashes,
    load_matter_body,
    matter_path,
    matter_slug,
    matter_unchanged,
    write_matter_file,
)


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_matter_slug_prefers_shared_tokens() -> None:
    assert matter_slug(["999888777"], []) == "matter-999888777"
    assert matter_slug(["111111", "222222"], []) == "matter-111111-222222"


def test_matter_slug_falls_back_to_a_hash_when_no_tokens(tmp_path: Path) -> None:
    slug = matter_slug([], [tmp_path / "a.md", tmp_path / "b.md"])

    assert slug.startswith("matter-")
    assert len(slug) == len("matter-") + 12


def test_write_matter_file_round_trips_type_and_hashes(tmp_path: Path) -> None:
    a = _write(tmp_path / "providers" / "providers.md")
    b = _write(tmp_path / "finances" / "finances.md")
    group = [a, b]

    path = write_matter_file(tmp_path, group, ["999888777"], "### Matter\n\nDense write-up.")

    assert path == matter_path(tmp_path, ["999888777"], group)
    content = path.read_text(encoding="utf-8")
    assert "type: Matter" in content
    assert "Dense write-up." in content
    assert "providers/providers.md" in content  # linked in the involved-aggregates list


def test_matter_unchanged_true_when_hashes_match(tmp_path: Path) -> None:
    a = _write(tmp_path / "providers" / "providers.md")
    group = [a]
    path = write_matter_file(tmp_path, group, ["999888777"], "### Matter\n\ntext")

    assert matter_unchanged(path, group_source_hashes(group, tmp_path)) is True


def test_matter_unchanged_false_when_a_member_changed(tmp_path: Path) -> None:
    a = _write(tmp_path / "providers" / "providers.md")
    group = [a]
    path = write_matter_file(tmp_path, group, ["999888777"], "### Matter\n\ntext")

    a.write_text("changed content", encoding="utf-8")

    assert matter_unchanged(path, group_source_hashes(group, tmp_path)) is False


def test_matter_unchanged_false_when_file_absent(tmp_path: Path) -> None:
    assert matter_unchanged(tmp_path / "matters" / "matter-1.md", {}) is False


def test_load_matter_body_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_matter_body(tmp_path / "matters" / "missing.md") is None
