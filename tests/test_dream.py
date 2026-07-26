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

    def verify_facts(self, source_text: str, extracted_markdown: str, *, max_tokens: int | None = None) -> str:
        return "OK"


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


def test_build_digest_includes_identifiers_from_frontmatter(tmp_path: Path) -> None:
    from app.models.okf import OKFDocument, OKFFrontmatter

    folder = tmp_path / "insurances"
    folder.mkdir()
    aggregate = folder / "insurances.md"
    aggregate.write_text(
        OKFDocument(
            frontmatter=OKFFrontmatter(
                type="FolderSummary",
                description=None,
                source=None,
                sources=["meldung.pdf"],
                identifiers={
                    "versicherungsnummer": ["13040393S105"],
                    "betriebsnummer": ["15027365", "32268191"],
                },
            ),
            body="## Meldung\n\nOrientation only in digest; body stays out.\n\n_Source: meldung.pdf_",
        ).to_markdown(),
        encoding="utf-8",
    )

    digest = build_digest(aggregate, tmp_path)

    assert "Identifiers:" in digest
    assert "versicherungsnummer: 13040393S105" in digest
    assert "betriebsnummer: 15027365, 32268191" in digest
    assert "Orientation only in digest" not in digest  # body still excluded


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


def test_dream_deprioritizes_trivial_folders_out_of_the_pass(tmp_path: Path) -> None:
    _build_tree(tmp_path)
    # A folder whose name carries a built-in trivial keyword is eagerly deprioritized.
    handbuch = tmp_path / "handbuch"
    handbuch.mkdir()
    (handbuch / "manual.txt").write_text("router setup steps", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]

    result = dream(str(tmp_path), client=_DreamStub())  # type: ignore[arg-type]

    # providers + finances feed dream; the handbuch aggregate does not.
    assert result.aggregate_count == 2


class _DeepDiveStub(_DreamStub):
    def dream_matter(self, evidence: str, *, max_tokens: int | None = None) -> str:
        return "### Matter\n\nACME dispute 1234.\n\n### Conflicts\n\nNone.\n\n### Actions\n\nFollow up."


def test_pertinence_principle_forms_a_matter_from_a_shorter_shared_id(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    finances = tmp_path / "finances"
    providers.mkdir()
    finances.mkdir()
    # A 4-digit shared id in the filename (so it lands in the digest's Sources line):
    # ignored under provenance (5-digit floor), a matter under pertinence.
    (providers / "contract_1234.txt").write_text("Kundennummer 1234 ACME", encoding="utf-8")
    (finances / "statement_1234.txt").write_text("Zahlung ref 1234 ACME", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]

    dream(str(tmp_path), client=_DeepDiveStub(), ordering_principle="provenance")  # type: ignore[arg-type]
    provenance_matters = list((tmp_path / "matters").glob("*.md")) if (tmp_path / "matters").is_dir() else []
    assert provenance_matters == []  # 4-digit id below the conservative floor

    dream(str(tmp_path), client=_DeepDiveStub(), ordering_principle="pertinence", force=True)  # type: ignore[arg-type]
    pertinence_matters = list((tmp_path / "matters").glob("*.md")) if (tmp_path / "matters").is_dir() else []
    assert pertinence_matters, "pertinence should have formed a matter from the 4-digit id"


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


class _TwoPassStub:
    """Baseline dream_synthesis (cheap) + a distinguishable dream_matter (deep dive)."""

    def __init__(self) -> None:
        self.synthesis_calls: list[str] = []
        self.matter_calls: list[str] = []

    def dream_synthesis(self, digest: str, *, max_tokens: int | None = None) -> str:
        self.synthesis_calls.append(digest)
        return (
            "## Matters\n\nBaseline vague matter mention.\n\n"
            "## Conflicts\n\nKeine Konflikte erkannt.\n\n"
            "## Patterns\n\n- Recurring provider correspondence.\n\n"
            "## Open actions\n\n- Baseline generic action."
        )

    def dream_matter(self, group_text: str, *, max_tokens: int | None = None) -> str:
        self.matter_calls.append(group_text)
        return (
            "### Matter\n\nDense matter write-up citing exact contract 999888777.\n\n"
            "### Conflicts\n\nTwo suppliers both claim exclusive delivery for the same period.\n\n"
            "### Actions\n\n- Verify the billing period against the network operator."
        )


def _build_tree_with_shared_filename_token(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    finances = tmp_path / "finances"
    providers.mkdir()
    finances.mkdir()
    # Real-world naming convention: the shared reference number lives in the filename,
    # which build_digest's "Sources:" line picks up even without reading section bodies.
    (providers / "invoice_999888777.txt").write_text("Invoice content", encoding="utf-8")
    (finances / "payment_999888777.txt").write_text("Payment content", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]


def test_deep_dive_replaces_matters_and_conflicts_but_keeps_baseline_patterns(tmp_path: Path) -> None:
    _build_tree_with_shared_filename_token(tmp_path)
    client = _TwoPassStub()

    result = dream(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert result.errors == []
    output = synthesis_path(tmp_path).read_text(encoding="utf-8")
    assert "Dense matter write-up citing exact contract 999888777" in output
    assert "Baseline vague matter mention" not in output  # replaced, not appended
    assert "Two suppliers both claim exclusive delivery" in output  # deep-dive conflict surfaced
    assert "Recurring provider correspondence" in output  # baseline Patterns kept
    assert "Baseline generic action" in output  # baseline actions preserved
    assert "Verify the billing period" in output  # deep-dive actions merged in
    assert len(client.matter_calls) == 1  # one candidate group -> one deep dive, not one per aggregate


def test_no_shared_tokens_means_no_deep_dive_and_identical_baseline_output(tmp_path: Path) -> None:
    _build_tree(tmp_path)  # existing fixture: no shared numeric tokens in digest text
    client = _TwoPassStub()

    dream(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert client.matter_calls == []  # grouping found nothing -> zero extra LLM calls
    output = synthesis_path(tmp_path).read_text(encoding="utf-8")
    assert "Baseline vague matter mention" in output  # baseline untouched


def test_parse_matter_sections_tolerant_of_missing_headers() -> None:
    from app.services.dream import _parse_matter_sections

    matter, conflicts, actions = _parse_matter_sections("Just some free-form text, no headers at all.")

    assert matter == "Just some free-form text, no headers at all."
    assert conflicts == ""
    assert actions == ""


def test_parse_matter_sections_splits_on_headers() -> None:
    from app.services.dream import _parse_matter_sections

    text = "### Matter\n\nM text\n\n### Conflicts\n\nC text\n\n### Actions\n\n- A text"
    matter, conflicts, actions = _parse_matter_sections(text)

    assert matter == "M text"
    assert conflicts == "C text"
    assert actions == "- A text"


def test_split_and_join_sections_round_trip() -> None:
    from app.services.dream import _join_sections, _split_sections

    body = "## Matters\n\nM\n\n## Conflicts\n\nC\n\n## Patterns\n\nP\n\n## Open actions\n\nA"
    sections = _split_sections(body)

    assert sections == {"Matters": "M", "Conflicts": "C", "Patterns": "P", "Open actions": "A"}
    assert _join_sections(sections) == body


def test_dream_writes_a_dedicated_matter_file_for_a_candidate_group(tmp_path: Path) -> None:
    _build_tree_with_shared_filename_token(tmp_path)
    client = _TwoPassStub()

    result = dream(str(tmp_path), client=client)  # type: ignore[arg-type]

    assert result.errors == []
    matter_files = list((tmp_path / "matters").glob("*.md"))
    assert len(matter_files) == 1
    content = matter_files[0].read_text(encoding="utf-8")
    assert "type: Matter" in content
    assert "999888777" in content
    assert "Dense matter write-up citing exact contract 999888777" in content
    assert "providers/providers.md" in content  # involved-aggregates link


def test_dream_reuses_matter_file_and_skips_deep_dive_when_group_unchanged(tmp_path: Path) -> None:
    _build_tree_with_shared_filename_token(tmp_path)
    dream(str(tmp_path), client=_TwoPassStub())  # type: ignore[arg-type]

    # Unrelated change elsewhere still forces a full dream rerun (synthesis-level hash
    # differs), but the matter group itself is untouched — its deep dive must be skipped.
    (tmp_path / "health").mkdir()
    (tmp_path / "health" / "note.txt").write_text("dentist visit", encoding="utf-8")
    ingest_folder(str(tmp_path), client=_IngestStub())  # type: ignore[arg-type]

    rerun_client = _TwoPassStub()
    result = dream(str(tmp_path), client=rerun_client)  # type: ignore[arg-type]

    assert result.errors == []
    assert result.unchanged is False  # the new health/ aggregate did change the tree overall
    assert rerun_client.matter_calls == []  # matter group's own aggregates unchanged
    output = synthesis_path(tmp_path).read_text(encoding="utf-8")
    assert "Dense matter write-up citing exact contract 999888777" in output


def test_apply_deep_dives_skips_splicing_when_baseline_unparseable(tmp_path: Path) -> None:
    from app.services.dream import _apply_deep_dives

    client = _TwoPassStub()
    unparseable_baseline = "The model ignored the format and just wrote free prose."

    result = _apply_deep_dives(
        unparseable_baseline,
        [[tmp_path / "a.md"]],
        {},
        tmp_path,
        client,  # type: ignore[arg-type]
        verbose=False,
    )

    assert result == unparseable_baseline
    assert client.matter_calls == []  # never even attempted — nothing safe to splice into
