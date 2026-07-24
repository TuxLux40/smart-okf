"""Tests for the static, read-only HTML dashboard generator."""

import subprocess
from pathlib import Path

import pytest

from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.dashboard import (
    DashboardData,
    build_config_summary,
    collect_cron_lines,
    collect_dashboard_data,
    collect_markdown_entries,
    git_log_graph,
    render_dashboard,
    render_markdown_html,
)


def _write_aggregate(path: Path, *, okf_type: str = "FolderSummary", title: str = "Providers") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = OKFDocument(
        frontmatter=OKFFrontmatter(type=okf_type, title=title, description="A folder", source=None, sources=["a.pdf"]),
        body="## A\n\nSome content.\n\n_Source: a.pdf_",
    )
    path.write_text(document.to_markdown(), encoding="utf-8")


def test_collect_markdown_entries_finds_files_and_skips_hidden_dirs(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers" / "providers.md")
    hidden = tmp_path / ".okf-transcripts" / "fake.md"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("not an aggregate", encoding="utf-8")

    entries = collect_markdown_entries(tmp_path)

    assert len(entries) == 1
    assert entries[0].relative_path == "providers/providers.md"
    assert entries[0].okf_type == "FolderSummary"
    assert entries[0].title == "Providers"
    assert "_Source: a.pdf_" in entries[0].raw_markdown
    assert entries[0].body == "## A\n\nSome content.\n\n_Source: a.pdf_"
    assert entries[0].sources == ["a.pdf"]


def test_render_markdown_html_covers_headers_lists_inline_and_citation() -> None:
    rendered = render_markdown_html(
        "## Vertrag\n\nDas **Wichtigste** zuerst.\n\n- Punkt eins\n- Punkt zwei\n\n_Source: a.pdf_"
    )

    assert "<h2>Vertrag</h2>" in rendered
    assert "<strong>Wichtigste</strong>" in rendered
    assert "<ul><li>Punkt eins</li><li>Punkt zwei</li></ul>" in rendered
    assert '<p class="citation">Source: a.pdf</p>' in rendered


def test_render_markdown_html_escapes_content_before_applying_markup() -> None:
    rendered = render_markdown_html("A document mentions <script>alert(1)</script> literally.")

    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_git_log_graph_returns_placeholder_for_non_git_dir(tmp_path: Path) -> None:
    graph = git_log_graph(tmp_path)

    assert "not a git repository" in graph or "unavailable" in graph


def test_git_log_graph_returns_commits_for_real_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True, check=True)
    (tmp_path / "file.txt").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True, check=True)

    graph = git_log_graph(tmp_path)

    assert "initial" in graph


def test_build_config_summary_none_reports_missing_config() -> None:
    summary = build_config_summary(None)

    assert "no valid smart-okf.yaml" in summary["status"]


def test_collect_cron_lines_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # Environments without a crontab (or without the `crontab` binary) must degrade
    # to an empty list rather than raising.
    lines = collect_cron_lines()

    assert isinstance(lines, list)


def test_render_dashboard_embeds_all_sections_and_escapes_html(tmp_path: Path) -> None:
    entries_source = tmp_path / "providers" / "providers.md"
    _write_aggregate(entries_source, title="<script>alert(1)</script>")

    data = DashboardData(
        root=tmp_path,
        entries=collect_markdown_entries(tmp_path),
        git_graph="* abc123 (HEAD) initial",
        config_summary={"llm_model": "qwen2.5:3b"},
        cron_lines=["0 3 * * 0 ingest_folder.py"],
    )

    html_output = render_dashboard(data)

    assert "<h1>smart-okf dashboard</h1>" in html_output
    assert "Markdown browser (1 files)" in html_output
    assert "abc123 (HEAD) initial" in html_output
    assert "qwen2.5:3b" in html_output
    assert "ingest_folder.py" in html_output
    # The malicious title must be escaped, not injected as live markup.
    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_output


def test_collect_dashboard_data_end_to_end(tmp_path: Path) -> None:
    _write_aggregate(tmp_path / "providers" / "providers.md")

    data = collect_dashboard_data(tmp_path, config=None)

    assert len(data.entries) == 1
    assert data.config_summary["status"]
    assert isinstance(data.cron_lines, list)
