"""Tests for the per-folder aggregate ingest pipeline."""

from pathlib import Path

from app.services.ingest import folder_summary_path, ingest_folder


class _StubLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def extract_structured(self, raw_text: str, context: str = "") -> str:
        self.calls += 1
        return f"---\ntype: Fact\ndescription: extracted\n---\n\nExtracted: {raw_text.strip()}"

    def summarize_sections(self, merged_sections: str) -> str:
        return ""


def test_folder_summary_path_is_folder_name_plus_md(tmp_path: Path) -> None:
    directory = tmp_path / "providers"
    directory.mkdir()
    assert folder_summary_path(directory) == directory / "providers.md"


def test_ingest_writes_one_aggregate_per_folder_not_per_file(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    providers.mkdir()
    (providers / "isp.txt").write_text("ISP contract details", encoding="utf-8")
    (providers / "electricity.txt").write_text("Electricity provider details", encoding="utf-8")

    result = ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    assert result.written_paths == [providers / "providers.md"]
    assert not (providers / "isp.md").exists()
    assert not (providers / "electricity.md").exists()

    aggregate_text = (providers / "providers.md").read_text(encoding="utf-8")
    assert "isp.txt" in aggregate_text
    assert "electricity.txt" in aggregate_text
    assert "type: FolderSummary" in aggregate_text
    assert "sources:" in aggregate_text


def test_ingest_is_not_recursive_across_folder_boundaries(tmp_path: Path) -> None:
    parent = tmp_path / "health"
    child = parent / "2026"
    child.mkdir(parents=True)
    (parent / "summary.txt").write_text("Parent-level doc", encoding="utf-8")
    (child / "visit.txt").write_text("Child-level doc", encoding="utf-8")

    result = ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    written = set(result.written_paths)
    assert parent / "health.md" in written
    assert child / "2026.md" in written

    parent_summary = (parent / "health.md").read_text(encoding="utf-8")
    assert "visit.txt" not in parent_summary
    assert "summary.txt" in parent_summary


def test_reingest_of_unchanged_folder_makes_no_llm_calls(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("Some notes", encoding="utf-8")

    first_client = _StubLLMClient()
    ingest_folder(str(tmp_path), client=first_client)  # type: ignore[arg-type]
    assert first_client.calls == 1

    second_client = _StubLLMClient()
    result = ingest_folder(str(tmp_path), client=second_client)  # type: ignore[arg-type]

    assert second_client.calls == 0
    assert result.written_paths == []
    assert result.unchanged_dirs == [tmp_path]


def test_reingest_only_reextracts_changed_files(tmp_path: Path) -> None:
    (tmp_path / "stable.txt").write_text("Stays the same", encoding="utf-8")
    (tmp_path / "edited.txt").write_text("Version one", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    (tmp_path / "edited.txt").write_text("Version two", encoding="utf-8")
    client = _StubLLMClient()
    result = ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert client.calls == 1
    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert "Version two" in aggregate
    assert "Stays the same" in aggregate
    assert result.written_paths == [tmp_path / f"{tmp_path.name}.md"]


def test_ingest_skips_folder_named_after_reserved_filename(tmp_path: Path) -> None:
    reserved = tmp_path / "index"
    reserved.mkdir()
    (reserved / "notes.txt").write_text("Some notes", encoding="utf-8")

    result = ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    assert result.written_paths == []
    assert any("reserved" in reason for _, reason in result.skipped)


def test_inner_headings_are_demoted_so_sections_survive_reingest(tmp_path: Path) -> None:
    class _HeadingClient:
        calls = 0

        def extract_structured(self, raw_text: str, context: str = "") -> str:
            self.calls += 1
            return "---\ntype: Fact\n---\n\n## Inner Heading\n\nDetail line\n\n###### Deep\n\nMore"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    (tmp_path / "doc.txt").write_text("content", encoding="utf-8")
    client = _HeadingClient()
    ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    aggregate_path = tmp_path / f"{tmp_path.name}.md"
    text = aggregate_path.read_text(encoding="utf-8")
    assert "### Inner Heading" in text
    assert "###### Deep" in text  # h6 stays h6, not pushed past the markdown limit

    (tmp_path / "other.txt").write_text("second file", encoding="utf-8")
    ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    text = aggregate_path.read_text(encoding="utf-8")
    assert "Detail line" in text  # reused section kept its full body
    assert "More" in text


def test_ingest_writes_raw_transcripts_to_hidden_root_folder(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    providers.mkdir()
    (providers / "isp.txt").write_text("ISP contract raw text", encoding="utf-8")

    ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    transcript = tmp_path / ".okf-transcripts" / "providers" / "isp.txt.txt"
    assert transcript.read_text(encoding="utf-8") == "ISP contract raw text"


def test_ingest_walk_skips_hidden_directories(tmp_path: Path) -> None:
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "config.txt").write_text("not a document", encoding="utf-8")

    client = _StubLLMClient()
    result = ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert client.calls == 0
    assert result.written_paths == []


def test_aggregate_prepends_synthesized_orientation_summary(tmp_path: Path) -> None:
    class _SummarizingClient:
        def extract_structured(self, raw_text: str, context: str = "") -> str:
            return f"---\ntype: Fact\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            return "Orientation: two documents about the same matter."

    (tmp_path / "a.txt").write_text("first", encoding="utf-8")
    (tmp_path / "b.txt").write_text("second", encoding="utf-8")

    ingest_folder(str(tmp_path), client=_SummarizingClient())  # type: ignore[arg-type]

    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert "Orientation: two documents about the same matter." in aggregate
    summary_index = aggregate.index("Orientation:")
    first_section_index = aggregate.index("## ")
    assert summary_index < first_section_index


def test_aggregate_still_written_when_summary_synthesis_fails(tmp_path: Path) -> None:
    from app.exceptions import LLMClientError

    class _FailingSummaryClient:
        def extract_structured(self, raw_text: str, context: str = "") -> str:
            return f"---\ntype: Fact\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            raise LLMClientError("boom")

    (tmp_path / "a.txt").write_text("first", encoding="utf-8")
    result = ingest_folder(str(tmp_path), client=_FailingSummaryClient())  # type: ignore[arg-type]

    assert result.written_paths == [tmp_path / f"{tmp_path.name}.md"]
    assert any("orientation summary skipped" in reason for _, reason in result.skipped)
