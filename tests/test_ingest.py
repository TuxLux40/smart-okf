"""Tests for the per-folder aggregate ingest pipeline."""

from pathlib import Path

import pytest

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


def test_merge_chunk_documents_fills_empty_first_chunk_identity() -> None:
    from app.models.okf import OKFDocument, OKFFrontmatter
    from app.services.ingest import merge_chunk_documents

    first = OKFDocument(
        frontmatter=OKFFrontmatter(type="Fact", title=None, description=None, source=None),
        body="part one",
    )
    second = OKFDocument(
        frontmatter=OKFFrontmatter(
            type="Fact", title="Invoice 42", description="Paid already", tags=["billing"], source=None
        ),
        body="part two",
    )
    merged = merge_chunk_documents([first, second])
    assert merged.frontmatter.title == "Invoice 42"
    assert merged.frontmatter.description == "Paid already"
    assert merged.frontmatter.tags == ["billing"]
    assert "part one" in merged.body and "part two" in merged.body


def test_oversized_document_is_chunked_and_merged_into_one_section(tmp_path: Path) -> None:
    import re

    class _CountingChunkClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def extract_structured(self, raw_text: str, context: str = "") -> str:
            self.calls.append(context)
            return f"---\ntype: Fact\ntitle: Big Doc\n---\n\n## Facts\n- chunk: {raw_text[:15]}"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    big_text = "This is a paragraph of text. " * 2000  # far exceeds CHUNK_CHAR_THRESHOLD
    (tmp_path / "big.txt").write_text(big_text, encoding="utf-8")
    client = _CountingChunkClient()

    result = ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert len(client.calls) > 1
    assert all("part" in call for call in client.calls)
    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^## ", aggregate, flags=re.MULTILINE)) == 1  # exactly one real h2 section
    assert aggregate.count("### Facts") > 1  # each chunk's own heading demoted, not dropped
    assert aggregate.count("_Source: big.txt_") == 1
    assert result.written_paths == [tmp_path / f"{tmp_path.name}.md"]


def test_image_routes_through_vision_model_when_configured(tmp_path: Path) -> None:
    class _VisionClient:
        vision_model = "qwen3-vl-8b-instruct"

        def __init__(self) -> None:
            self.described: list[str] = []

        def describe_image(self, image_path: Path, *, context: str = "") -> str:
            self.described.append(context)
            return "Meter reading: 042317 kWh. A power meter mounted on a wall."

        def extract_structured(self, raw_text: str, context: str = "") -> str:
            return f"---\ntype: Fact\ntitle: Meter\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    (tmp_path / "meter.jpg").write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    client = _VisionClient()

    result = ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert client.described == ["meter.jpg"]
    assert result.written_paths == [tmp_path / f"{tmp_path.name}.md"]
    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert "Meter reading: 042317 kWh" in aggregate
    transcript = (tmp_path / ".okf-transcripts" / "meter.jpg.txt").read_text(encoding="utf-8")
    assert "power meter mounted on a wall" in transcript


def test_image_falls_back_to_tesseract_when_no_vision_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ingest as ingest_module

    class _NoVisionClient:
        vision_model = None

        def extract_structured(self, raw_text: str, context: str = "") -> str:
            return f"---\ntype: Fact\ntitle: Meter\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    def _fake_extract_text_from_file(file_path: Path, options: object = None) -> str:
        assert file_path.suffix == ".jpg"
        return "tesseract OCR output"

    monkeypatch.setattr(ingest_module, "extract_text_from_file", _fake_extract_text_from_file)
    (tmp_path / "meter.jpg").write_bytes(b"\xff\xd8\xff fake jpeg bytes")

    result = ingest_folder(str(tmp_path), client=_NoVisionClient())  # type: ignore[arg-type]

    assert result.written_paths == [tmp_path / f"{tmp_path.name}.md"]
    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert "tesseract OCR output" in aggregate


def test_orphan_aggregate_removed_when_folder_emptied(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("content", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]
    aggregate_path = tmp_path / f"{tmp_path.name}.md"
    assert aggregate_path.is_file()

    (tmp_path / "doc.txt").unlink()
    result = ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    assert not aggregate_path.exists()
    assert result.removed_paths == [aggregate_path]


def test_hand_written_markdown_sharing_folder_name_is_never_deleted(tmp_path: Path) -> None:
    # Not our output: no FolderSummary frontmatter. Folder has no supported files.
    hand_written = tmp_path / f"{tmp_path.name}.md"
    hand_written.write_text("# My own notes\n\nDo not touch.", encoding="utf-8")

    result = ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]

    assert hand_written.is_file()
    assert result.removed_paths == []


def test_failed_reextraction_keeps_previous_section_and_retries_next_run(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("version one", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_StubLLMClient())  # type: ignore[arg-type]
    aggregate_path = tmp_path / f"{tmp_path.name}.md"
    assert "version one" in aggregate_path.read_text(encoding="utf-8")

    class _FailingClient:
        def extract_structured(self, raw_text: str, context: str = "") -> str:
            raise RuntimeError("LLM down")

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    (tmp_path / "doc.txt").write_text("version two", encoding="utf-8")
    result = ingest_folder(str(tmp_path), client=_FailingClient())  # type: ignore[arg-type]

    # Old section survives; skip is recorded; next run still sees a hash mismatch.
    text = aggregate_path.read_text(encoding="utf-8")
    assert "version one" in text
    assert any("LLM down" in reason for _, reason in result.skipped)

    retry = _StubLLMClient()
    ingest_folder(str(tmp_path), client=retry)  # type: ignore[arg-type]
    assert retry.calls == 1
    assert "version two" in aggregate_path.read_text(encoding="utf-8")


def test_arbitrary_exception_in_one_file_does_not_abort_run(tmp_path: Path) -> None:
    class _ExplodingOnBClient:
        def extract_structured(self, raw_text: str, context: str = "") -> str:
            if "boom" in raw_text:
                raise ValueError("totally unexpected parser explosion")
            return f"---\ntype: Fact\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    (tmp_path / "a.txt").write_text("fine content", encoding="utf-8")
    (tmp_path / "b.txt").write_text("boom", encoding="utf-8")

    result = ingest_folder(str(tmp_path), client=_ExplodingOnBClient())  # type: ignore[arg-type]

    aggregate = (tmp_path / f"{tmp_path.name}.md").read_text(encoding="utf-8")
    assert "fine content" in aggregate
    assert any("parser explosion" in reason for _, reason in result.skipped)


def test_exit_code_reflects_skips_and_bad_root(tmp_path: Path) -> None:
    from app.services.ingest import IngestFolderResult

    clean = IngestFolderResult(root=tmp_path)
    assert clean.exit_code == 0

    partial = IngestFolderResult(root=tmp_path, skipped=[(tmp_path / "x.pdf", "reason")])
    assert partial.exit_code == 2

    bad = IngestFolderResult(root=tmp_path / "does-not-exist")
    assert bad.exit_code == 1


def test_backfill_skips_images_when_vision_model_configured(tmp_path: Path) -> None:
    class _VisionBackfillClient:
        vision_model = "some-vl-model"

        def describe_image(self, image_path: Path, *, context: str = "") -> str:
            return "vision transcription of the meter"

        def extract_structured(self, raw_text: str, context: str = "") -> str:
            return f"---\ntype: Fact\ntitle: Meter\n---\n\nExtracted: {raw_text.strip()}"

        def summarize_sections(self, merged_sections: str) -> str:
            return ""

    (tmp_path / "meter.jpg").write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    client = _VisionBackfillClient()
    ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]

    transcript = tmp_path / ".okf-transcripts" / "meter.jpg.txt"
    assert transcript.is_file()
    transcript.unlink()

    # Unchanged re-ingest must NOT backfill a contradicting tesseract transcript.
    ingest_folder(str(tmp_path), client=client)  # type: ignore[arg-type]
    assert not transcript.exists()
