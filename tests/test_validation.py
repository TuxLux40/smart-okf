"""Tests for heuristic plausibility checks on OKF aggregate/matter documents."""

from pathlib import Path

from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.validation import validate_aggregate, validate_tree

_DUMMY_PATH = Path("dummy.md")


def _document(*, sources: list[str], body: str, doc_type: str = "FolderSummary") -> OKFDocument:
    return OKFDocument(
        frontmatter=OKFFrontmatter(type=doc_type, description=None, source=None, sources=sources),
        body=body,
    )


def test_genuine_extraction_passes_all_checks() -> None:
    document = _document(
        sources=["a.pdf", "b.pdf"],
        body=(
            "## Vertrag A\n\nDetails about the first document with real facts, dates, and "
            "figures spanning well more than eighty characters of substance.\n\n_Source: a.pdf_\n\n"
            "## Vertrag B\n\nDetails about the second document, again with genuine content well "
            "past the density floor.\n\n_Source: b.pdf_"
        ),
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    assert report.passed
    assert report.failures == []


def test_empty_sources_fails() -> None:
    document = _document(sources=[], body="Material zu Marketing und Absatzwirtschaft.")

    report = validate_aggregate(document, _DUMMY_PATH)

    assert not report.passed
    assert any("sources: is non-empty" in f.text for f in report.failures)


def test_missing_source_citation_fails() -> None:
    document = _document(
        sources=["a.pdf", "b.pdf"],
        body="## A\n\nSome real content about a.pdf that is reasonably long.\n\n_Source: a.pdf_",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    assert not report.passed
    failure = next(f for f in report.failures if "matching _Source:" in f.text)
    assert "b.pdf" in failure.evidence


def test_root_relative_source_path_matches_bare_filename_citation() -> None:
    # `ingest.py` writes `sources:` as paths relative to the document root
    # (`unsorted/Vitals/a.csv`) but `_Source:` lines as the bare filename
    # (`file_path.name` — see `ingest.py:_render_section`). A real aggregate that cites
    # every source correctly must not be flagged just because it isn't at the root.
    document = _document(
        sources=["unsorted/Vitals/a.csv", "unsorted/Vitals/b.csv"],
        body=(
            "## A\n\nGenuine content about a.csv, well past the density floor.\n\n_Source: a.csv_\n\n"
            "## B\n\nGenuine content about b.csv, well past the density floor.\n\n_Source: b.csv_"
        ),
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    assert report.passed


def test_thin_body_relative_to_source_count_fails() -> None:
    # Mirrors the real fabricated-aggregate shape: many sources, one generic sentence.
    document = _document(
        sources=[f"doc{i}.pdf" for i in range(12)],
        body="Diese Sammlung umfasst 12 Dokumente zu Aspekten der FaMI-Ausbildung im Bereich Marketing.",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    assert not report.passed
    assert any("characters per source" in f.text for f in report.failures)


def test_tiny_folder_with_short_but_real_body_can_still_pass_density() -> None:
    # One source, body just over the density floor - not flagged purely for being short.
    document = _document(
        sources=["note.pdf"],
        body="## Note\n\nA short but genuine note with specific extracted content here.\n\n_Source: note.pdf_",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    density_finding = next(f for f in report.findings if "characters per source" in f.text)
    assert density_finding.passed


def test_validate_tree_only_includes_folder_summary_and_matter_types(tmp_path: Path) -> None:
    good = tmp_path / "providers"
    good.mkdir()
    (good / "providers.md").write_text(
        OKFDocument(
            frontmatter=OKFFrontmatter(type="FolderSummary", description=None, source=None, sources=["a.pdf"]),
            body="## A\n\nGenuine per-document content well past the density floor for one source.\n\n_Source: a.pdf_",
        ).to_markdown(),
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("# Hand-written notes, no frontmatter", encoding="utf-8")

    reports = validate_tree(tmp_path)

    assert len(reports) == 1
    assert reports[0].path == good / "providers.md"
    assert reports[0].passed


def test_leaked_nested_frontmatter_fails() -> None:
    # Real failure shape: model pasted its own sub-extraction verbatim instead of merging it.
    document = _document(
        sources=["a.csv"],
        body=(
            "## A\n\n```markdown\n---\ntype: Fact\ntitle: Something\n---\n"
            "### Key Facts\n* value\n```\n\n_Source: a.csv_"
        ),
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    failure = next(f for f in report.failures if "leaked into the body" in f.text)
    assert "1 bare" in failure.evidence


def test_template_placeholder_fails() -> None:
    document = _document(
        sources=["a.csv"],
        body="## A\n\ntitle: ...\nsource: path/to/original.csv\n\nSome real content here.\n\n_Source: a.csv_",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    failure = next(f for f in report.failures if "placeholder" in f.text)
    assert "title" in failure.evidence
    assert "source" in failure.evidence


def test_repeated_block_with_changing_digits_fails() -> None:
    # Mirrors the real repetition-loop shape: same paragraph, only the timestamp changes.
    block = "Date: 2020-02-15\nTime: 14:{:02d}:00\nDevice: Garmin\nMeasurement: weight data"
    body = "\n\n".join(block.format(minute) for minute in (12, 18, 20, 22)) + "\n\n_Source: a.csv_"
    document = _document(sources=["a.csv"], body=body)

    report = validate_aggregate(document, _DUMMY_PATH)

    failure = next(f for f in report.failures if "degenerate loop" in f.text)
    assert "4x" in failure.evidence


def test_meta_commentary_phrase_fails() -> None:
    document = _document(
        sources=["a.csv"],
        body="## A\n\nHere is the output in valid OKF markdown:\n\nSome content.\n\n_Source: a.csv_",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    failure = next(f for f in report.failures if "meta-commentary" in f.text)
    assert "here is the output" in failure.evidence


def test_matter_type_cites_via_prose_not_source_marker() -> None:
    # Real shape written by matter_files.write_matter_file: a deterministic "Involved
    # aggregates" link list embedding the full source path, plus free-form deep-dive
    # prose that cites via "Quelle: *path*" — never a `_Source: <name>_` marker line.
    document = _document(
        sources=["psychology_psychiatry/LVR_Klinik/LVR_Klinik.md"],
        body=(
            "## Involved aggregates\n\n"
            "- [psychology_psychiatry/LVR_Klinik/LVR_Klinik.md](../psychology_psychiatry/LVR_Klinik/LVR_Klinik.md)\n\n"
            "### Matter\n\nDense, real, well-cited write-up citing the source aggregate above.\n\n"
            "### Conflicts\n\nKeine Konflikte erkannt.\n\n### Actions\n\n- Follow up with the clinic."
        ),
        doc_type="Matter",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    assert report.passed


def test_matter_type_flags_missing_source_reference() -> None:
    document = _document(
        sources=["psychology_psychiatry/LVR_Klinik/LVR_Klinik.md"],
        body="### Matter\n\nSome real content that never mentions the source path at all here.",
        doc_type="Matter",
    )

    report = validate_aggregate(document, _DUMMY_PATH)

    failure = next(f for f in report.failures if "referenced in the body" in f.text or "appears in the body" in f.text)
    assert "LVR_Klinik.md" in failure.evidence


def test_validate_tree_skips_hidden_directories(tmp_path: Path) -> None:
    hidden = tmp_path / ".okf-transcripts"
    hidden.mkdir()
    (hidden / "fake.md").write_text(
        OKFDocument(
            frontmatter=OKFFrontmatter(type="FolderSummary", description=None, source=None, sources=[]),
            body="",
        ).to_markdown(),
        encoding="utf-8",
    )

    reports = validate_tree(tmp_path)

    assert reports == []
