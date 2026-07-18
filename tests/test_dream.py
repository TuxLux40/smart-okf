"""Tests for the cross-folder dream synthesis pass."""

from pathlib import Path

import pytest

from app.services.dream import _batch_digests, build_digest, collect_aggregates, dream, synthesis_path
from app.services.ingest import ingest_folder


class _IngestStub:
    def extract_structured(self, raw_text: str, context: str = "") -> str:
        return f"---\ntype: Fact\ntags: [Vertrag]\n---\n\nExtracted: {raw_text.strip()}"

    def summarize_sections(self, merged_sections: str) -> str:
        return "Orientation summary for this folder."


class _DreamStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dream_synthesis(self, digest: str, *, max_tokens: int | None = None) -> str:
        self.calls.append(digest)
        return (
            "## Matters\n\n- **Energy dispute** `providers/providers.md`\n\n"
            "## Conflicts\n\nNo conflicts detected.\n\n"
            "## Patterns\n\n- Recurring provider letters.\n\n"
            "## Open actions\n\n- Verify meter reading."
        )


def _build_tree(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    finances = tmp_path / "finances"
    providers.mkdir()
    finances.mkdir()
    (providers / "contract.txt").write_text("Contract 123456789 with ACME Energy", encoding="utf-8")
    (finances / "statement.txt").write_text("Payment to ACME Energy, ref 123456789", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]


def test_collect_aggregates_finds_folder_summaries_not_other_markdown(tmp_path: Path) -> None:
    _build_tree(tmp_path)
    (tmp_path / "notes.md").write_text("# Hand-written notes, no frontmatter", encoding="utf-8")

    found = collect_aggregates(tmp_path)

    assert tmp_path / "providers" / "providers.md" in found
    assert tmp_path / "finances" / "finances.md" in found
    assert tmp_path / "notes.md" not in found


def test_build_digest_is_compact_identity_not_full_body(tmp_path: Path) -> None:
    _build_tree(tmp_path)

    digest = build_digest(tmp_path / "providers" / "providers.md", tmp_path)

    assert "### Aggregate: providers/providers.md" in digest
    assert "Orientation summary for this folder." in digest
    assert "_Source: contract.txt_" in digest
    assert "Extracted: Contract 123456789" not in digest  # section bodies stay out


def test_dream_writes_synthesis_with_type_and_hashes(tmp_path: Path) -> None:
    _build_tree(tmp_path)
    client = _DreamStub()

    result = dream(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert result.errors == []
    assert result.aggregate_count == 2
    output = synthesis_path(tmp_path).read_text(encoding="utf-8")
    assert "type: Synthesis" in output
    assert "## Matters" in output
    assert "providers/providers.md" in output  # hash entry + citation
    assert len(client.calls) == 1


def test_dream_is_incremental_and_force_overrides(tmp_path: Path) -> None:
    _build_tree(tmp_path)
    dream(str(tmp_path), client=_DreamStub())  # type: ignore[arg-type]

    second = _DreamStub()
    result = dream(str(tmp_path), client=second)  # type: ignore[arg-type]
    assert result.unchanged is True
    assert second.calls == []

    forced = _DreamStub()
    result = dream(str(tmp_path), client=forced, force=True)  # type: ignore[arg-type]
    assert result.unchanged is False
    assert len(forced.calls) == 1


def test_dream_reruns_when_an_aggregate_changed(tmp_path: Path) -> None:
    _build_tree(tmp_path)
    dream(str(tmp_path), client=_DreamStub())  # type: ignore[arg-type]

    (tmp_path / "providers" / "new_letter.txt").write_text("New demand, ref 123456789", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]

    rerun = _DreamStub()
    result = dream(str(tmp_path), client=rerun)  # type: ignore[arg-type]
    assert result.unchanged is False
    assert len(rerun.calls) == 1


def test_dream_without_aggregates_errors_cleanly(tmp_path: Path) -> None:
    result = dream(str(tmp_path), client=_DreamStub())  # type: ignore[arg-type]

    assert result.exit_code == 1
    assert any("run ingest first" in error for error in result.errors)


def test_dream_batches_oversized_digests_and_consolidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build_tree(tmp_path)
    client = _DreamStub()

    monkeypatch.setattr("app.services.dream.CHUNK_CHAR_THRESHOLD", 50)  # force multiple batches
    result = dream(str(tmp_path), client=client, force=True)  # type: ignore[arg-type]

    assert result.errors == []
    assert len(client.calls) == 3  # 2 partial batches + 1 consolidation
    assert "Partial synthesis" in client.calls[-1]


def test_batch_digests_respects_budget() -> None:
    digests = ["a" * 40, "b" * 40, "c" * 40]

    batches = _batch_digests(digests, budget=100)

    assert len(batches) == 2
    assert "".join(batches).count("a") == 40
