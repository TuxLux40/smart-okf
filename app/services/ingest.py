"""Document ingest helpers shared by CLI and agents.

Writes one aggregate OKF markdown file per folder (non-recursive: a folder's aggregate
covers only the files directly inside it, not files in subfolders) rather than one
companion per source document, to keep folders with many documents from becoming
cluttered with individual `.md` files.

Ingest is incremental: each aggregate stores a SHA-256 per source file in its
`source_hashes` frontmatter. On re-ingest, unchanged files reuse their existing body
section without an LLM call; a folder whose files are all unchanged is skipped entirely.
"""

import contextlib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.constants import (
    FACTS_DIR_NAME,
    FOLDER_INDEX_OKF_TYPE,
    FOLDER_SUMMARY_OKF_TYPE,
    IMAGE_DOCUMENT_SUFFIXES,
    LLM_LOG_FILENAME,
    RESERVED_CONCEPT_FILENAMES,
    ROLLUP_HEADING,
    TRANSCRIPTS_DIR_NAME,
)
from app.exceptions import DocumentIngestError, LLMClientError
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.chunking import chunk_text
from app.services.extraction_options import DEFAULT_EXTRACTION, LIGHT_EXTRACTION, ExtractionOptions
from app.services.fact_verification import FactVerificationResult, verify_extraction
from app.services.gating import GatingRules, is_excluded
from app.services.llm_client import LLMClient
from app.services.text_extraction import extract_text_from_file, is_supported_document
from app.types import FrontmatterPatch

_SOURCE_MARKER_PATTERN = re.compile(r"^_Source: (?P<name>.+)_$", re.MULTILINE)
_ROLLUP_SECTION_PATTERN = re.compile(re.escape(ROLLUP_HEADING) + r"\n.*?(?=\n## |\Z)", re.DOTALL)


@dataclass
class IngestFolderResult:
    """Summary of a folder ingest run."""

    root: Path
    written_paths: list[Path] = field(default_factory=list)
    unchanged_dirs: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    removed_paths: list[Path] = field(default_factory=list)
    flagged: list[tuple[Path, str]] = field(default_factory=list)
    """Files whose extraction was written but failed fact verification — the section is
    kept (never silently dropped) and marked in the aggregate body with a
    `_Verification: FLAGGED — <reason>_` line; this list is the same information for a
    CLI/caller summary without re-parsing every aggregate."""

    @property
    def exit_code(self) -> int:
        """Process exit code for CLI callers: 1 bad root, 2 partial (skips/flags), 0 clean.

        Nonzero on skips or flags so cron/scheduled runs go red instead of silently
        "green" while files fail to ingest or fail fact verification.
        """
        if not self.root.is_dir():
            return 1
        if self.skipped or self.flagged:
            return 2
        return 0


def apply_ingest_defaults(
    document: OKFDocument,
    file_path: Path,
    root: Path,
) -> OKFDocument:
    """Fill missing provenance fields without mutating the input document."""
    relative_source = str(file_path.relative_to(root))
    frontmatter_updates: FrontmatterPatch = {}

    if not document.frontmatter.source:
        frontmatter_updates["source"] = relative_source
    if not document.frontmatter.title:
        frontmatter_updates["title"] = file_path.stem.replace("_", " ").title()

    if not frontmatter_updates:
        return document

    updated_frontmatter = document.frontmatter.model_copy(update=frontmatter_updates)
    return document.model_copy(update={"frontmatter": updated_frontmatter})


def folder_summary_path(directory: Path) -> Path:
    """Return the aggregate markdown path for a folder: `<folder>/<folder-name>.md`."""
    return directory / f"{directory.name}.md"


def hash_file(file_path: Path) -> str:
    """Return the streaming SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transcript_path(file_path: Path, root: Path) -> Path:
    """Return the raw-transcript sidecar path for a source file: `<root>/.okf-transcripts/<relpath>.txt`."""
    relative = file_path.relative_to(root)
    return root / TRANSCRIPTS_DIR_NAME / relative.parent / f"{relative.name}.txt"


def write_transcript(file_path: Path, root: Path, raw_text: str) -> None:
    """Store the full raw extracted text so OCR/extraction never has to repeat.

    Aggregates are curated LLM output; the transcript is the lossless record agents
    (or a future re-ingest with a better model) can reuse without touching the original.
    """
    target = transcript_path(file_path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw_text, encoding="utf-8")


def extract_document(
    file_path: Path,
    root: Path,
    client: LLMClient,
    *,
    options: ExtractionOptions = DEFAULT_EXTRACTION,
    verify_client: LLMClient | None = None,
) -> tuple[OKFDocument, FactVerificationResult]:
    """Extract and structure one document into an OKF document (no aggregate write).

    Documents too large for a single LLM call are chunked (`chunk_text`) and extracted
    per chunk, then merged (`merge_chunk_documents`) — this always returns exactly one
    document, preserving the one-file-one-aggregate-section invariant regardless of how
    many LLM calls it took.

    Always followed by one fact-verification call against the raw text already read
    above (never a second OCR/re-read) — mandatory, not opt-in; `verify_client` lets a
    separate (e.g. bigger) model do the checking, defaulting to `client` itself so
    verification runs even when no separate verifier is configured.
    """
    context = str(file_path.relative_to(root))
    if file_path.suffix.lower() in IMAGE_DOCUMENT_SUFFIXES and client.vision_model is not None:
        raw_text = client.describe_image(file_path, context=context)
    else:
        raw_text = extract_text_from_file(file_path, options)
    if not raw_text.strip():
        raise DocumentIngestError(f"No extractable text in {file_path}")
    write_transcript(file_path, root, raw_text)

    chunks = chunk_text(raw_text)
    documents: list[OKFDocument] = []
    for i, chunk in enumerate(chunks):
        chunk_context = context if len(chunks) == 1 else f"{context} (part {i + 1}/{len(chunks)})"
        extracted_markdown = client.extract_structured(chunk, context=chunk_context)
        try:
            documents.append(OKFDocument.from_markdown(extracted_markdown))
        except Exception as error:
            raise DocumentIngestError(f"Failed to parse OKF markdown for {file_path}") from error

    document = merge_chunk_documents(documents)
    document = apply_ingest_defaults(document, file_path, root)
    verification = verify_extraction(raw_text, document.body, verify_client or client)
    return document, verification


def merge_chunk_documents(documents: list[OKFDocument]) -> OKFDocument:
    """Merge multiple chunk-extracted documents (one file, split across LLM calls) into one.

    Prefer first-chunk identity (letterhead/subject usually lives at the top). Empty
    title/description/source on the first chunk are filled from later chunks when present.
    Tags are the ordered union across all chunks. Bodies concatenate in chunk order.
    """
    if not documents:
        raise ValueError("merge_chunk_documents requires at least one document")
    if len(documents) == 1:
        return documents[0]

    tags: list[str] = []
    for document in documents:
        for tag in document.frontmatter.tags:
            if tag not in tags:
                tags.append(tag)

    updates: FrontmatterPatch = {"tags": tags}
    base = documents[0].frontmatter
    for field_name in ("title", "description", "source"):
        if getattr(base, field_name):
            continue
        for document in documents[1:]:
            value = getattr(document.frontmatter, field_name)
            if value:
                updates[field_name] = value
                break

    frontmatter = base.model_copy(update=updates)
    body = "\n\n".join(document.body for document in documents if document.body.strip())
    return OKFDocument(frontmatter=frontmatter, body=body)


def render_section(file_path: Path, document: OKFDocument, verification: FactVerificationResult | None = None) -> str:
    """Render one source document's body section for the folder aggregate.

    Headings inside the document body are demoted one level (capped at h6) so the
    aggregate's `## <document>` sections stay the only h2s — `parse_existing_sections`
    splits on h2, and un-demoted inner h2s would fragment a section and silently
    truncate it on incremental re-ingest.

    A failed `verification` is rendered inline as a `_Verification: FLAGGED — <reason>_`
    line, right under `_Source:` — visible to anyone reading the aggregate directly
    (human or agent), not only to whoever happens to check `IngestFolderResult.flagged`.
    The section is still written either way: a flagged extraction might still contain
    real, useful facts, and this project's convention is to surface a problem rather
    than silently drop the data (same principle as keeping a stale section when
    re-extraction fails outright).
    """
    heading = document.frontmatter.title or file_path.name
    body = re.sub(r"^(#{1,5}) ", r"#\1 ", document.body, flags=re.MULTILINE)
    verification_line = (
        f"_Verification: FLAGGED — {verification.issue}_\n\n"
        if verification is not None and not verification.passed
        else ""
    )
    return f"## {heading}\n\n_Source: {file_path.name}_\n\n{verification_line}{body}"


def parse_existing_sections(summary: OKFDocument) -> dict[str, str]:
    """Map source filename -> full body section from an existing aggregate.

    Sections are `## ...` blocks carrying an `_Source: <filename>_` marker line; the
    marker (not the heading) identifies the source file, since headings come from
    LLM-extracted titles that may change between runs.
    """
    sections: dict[str, str] = {}
    blocks = re.split(r"(?=^## )", summary.body, flags=re.MULTILINE)
    for block in blocks:
        marker = _SOURCE_MARKER_PATTERN.search(block)
        if marker:
            sections[marker.group("name")] = block.strip()
    return sections


def load_existing_summary(summary_path: Path) -> OKFDocument | None:
    """Load a previously written aggregate, or None if absent/unreadable."""
    if not summary_path.is_file():
        return None
    try:
        return OKFDocument.from_markdown(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def facts_path(file_path: Path, root: Path) -> Path:
    """Return the per-file derived-facts sidecar path: `<root>/.okf-facts/<relpath>.md`."""
    relative = file_path.relative_to(root)
    return root / FACTS_DIR_NAME / relative.parent / f"{relative.name}.md"


def write_facts_file(file_path: Path, root: Path, document: OKFDocument) -> None:
    """Persist one document's extraction as a standalone facts file (opt-in per-file artifact).

    Additive only — the same facts are already in the folder aggregate; this mirrors the
    tree under `.okf-facts/` for callers who want a file per document. Hidden dir, like
    transcripts, so it never clutters the user's visible folders.
    """
    target = facts_path(file_path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document.to_markdown(), encoding="utf-8")


def ingest_folder(
    folder: str,
    client: LLMClient | None = None,
    *,
    options: ExtractionOptions = DEFAULT_EXTRACTION,
    verbose: bool = False,
    verify_client: LLMClient | None = None,
    rules: GatingRules | None = None,
    derive_per_file: bool = False,
    generate_readme: bool = True,
) -> IngestFolderResult:
    """Ingest supported documents from a folder, writing one aggregate `.md` per subfolder.

    `verify_client` runs the mandatory post-extraction fact check (see `extract_document`)
    — pass a separate (e.g. bigger/smarter) model to check the extractor's own output with
    a different model than the one that might have made the mistake; omit it to verify
    with the same client that did the extraction.

    `rules` gates ingest: files matching an exclude pattern are skipped entirely (logged),
    for documents carrying no durable facts (manuals, terms). `derive_per_file` additionally
    writes one `.okf-facts/<file>.md` per document (the facts are always in the aggregate
    regardless). `generate_readme` refreshes the human navigation `README.md` at the root.
    """
    root = Path(folder).expanduser().resolve()
    result = IngestFolderResult(root=root)
    if not root.is_dir():
        if verbose:
            print(f"Error: {root} is not a directory")
        return result

    llm_client = client or LLMClient(log_path=root / LLM_LOG_FILENAME)
    gating_rules = rules or GatingRules()
    if verbose:
        print(f"Scanning {root}...")

    directories = [root] + sorted(
        p for p in root.rglob("*") if p.is_dir() and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )
    for directory in directories:
        _ingest_directory(
            directory,
            root,
            llm_client,
            result,
            options=options,
            verbose=verbose,
            verify_client=verify_client,
            rules=gating_rules,
            derive_per_file=derive_per_file,
        )

    write_rollups(root, result, verbose=verbose)

    if generate_readme:
        # Local import avoids a module-level cycle (navigation imports from this module).
        from app.services.navigation import write_navigation

        if write_navigation(root) is None and verbose:
            print("  Navigation README left untouched (hand-written README.md found)")

    if verbose:
        print(
            f"Ingest complete. Wrote {len(result.written_paths)} aggregate(s), "
            f"{len(result.unchanged_dirs)} folder(s) unchanged."
        )

    return result


def _backfill_transcript(file_path: Path, root: Path, client: LLMClient) -> None:
    """Write a missing transcript for an already-ingested file, best-effort and read-only.

    Uses LIGHT_EXTRACTION: never shells into marker, never OCR-rewrites a scanned PDF —
    a pass over an unchanged folder must not mutate its files or cold-start heavy tools.
    Images are skipped when a vision model is configured: a tesseract-only transcript
    would contradict the vision-derived aggregate section, and the vision call is not
    "cheap backfill" territory — the transcript reappears on the next real re-ingest.
    """
    if file_path.suffix.lower() in IMAGE_DOCUMENT_SUFFIXES and client.vision_model is not None:
        return
    if transcript_path(file_path, root).exists():
        return
    with contextlib.suppress(DocumentIngestError):
        write_transcript(file_path, root, extract_text_from_file(file_path, LIGHT_EXTRACTION))


def _remove_orphan_aggregate(directory: Path, result: IngestFolderResult, *, verbose: bool) -> None:
    """Delete a stale aggregate left behind after a folder's last supported file was removed.

    Only deletes files that are verifiably our own output (`type: FolderSummary`
    frontmatter) — a hand-written markdown file that happens to share the folder's
    name is never touched. Reserved names are never aggregates, so nothing to do there.
    """
    summary_path = folder_summary_path(directory)
    if summary_path.name in RESERVED_CONCEPT_FILENAMES or not summary_path.is_file():
        return
    existing = load_existing_summary(summary_path)
    if existing is None or existing.frontmatter.type != FOLDER_SUMMARY_OKF_TYPE:
        return
    summary_path.unlink()
    result.removed_paths.append(summary_path)
    if verbose:
        print(f"  -> Removed orphan aggregate {summary_path} (no supported files left)")


def _ingest_directory(
    directory: Path,
    root: Path,
    client: LLMClient,
    result: IngestFolderResult,
    *,
    options: ExtractionOptions,
    verbose: bool,
    verify_client: LLMClient | None = None,
    rules: GatingRules | None = None,
    derive_per_file: bool = False,
) -> None:
    """Ingest the files directly inside one directory (non-recursive) into its aggregate."""
    gating_rules = rules or GatingRules()
    supported = sorted(f for f in directory.iterdir() if f.is_file() and is_supported_document(f))
    files: list[Path] = []
    for candidate in supported:
        if is_excluded(str(candidate.relative_to(root)), gating_rules):
            result.skipped.append((candidate, "excluded by gating pattern (not ingested)"))
            if verbose:
                print(f"  Excluded {candidate} (gating pattern)")
            continue
        files.append(candidate)
    if not files:
        _remove_orphan_aggregate(directory, result, verbose=verbose)
        return

    summary_path = folder_summary_path(directory)
    if summary_path.name in RESERVED_CONCEPT_FILENAMES:
        result.skipped.append(
            (directory, f"folder name {directory.name!r} would produce a reserved summary filename; rename the folder")
        )
        return

    current_hashes = {f.name: hash_file(f) for f in files}
    existing = load_existing_summary(summary_path)
    old_hashes = existing.frontmatter.source_hashes if existing else {}
    old_sections = parse_existing_sections(existing) if existing else {}

    if existing is not None and current_hashes == old_hashes:
        result.unchanged_dirs.append(directory)
        for file_path in files:
            _backfill_transcript(file_path, root, client)
        if verbose:
            print(f"Unchanged: {directory}")
        return

    sections: list[str] = []
    tags: list[str] = [] if existing is None else list(existing.frontmatter.tags)
    extracted_any = False
    ingested_files: list[Path] = []

    for file_path in files:
        reusable = current_hashes[file_path.name] == old_hashes.get(file_path.name)
        if reusable and file_path.name in old_sections:
            sections.append(old_sections[file_path.name])
            ingested_files.append(file_path)
            _backfill_transcript(file_path, root, client)
            continue

        if verbose:
            print(f"Processing: {file_path}")
        try:
            document, verification = extract_document(
                file_path, root, client, options=options, verify_client=verify_client
            )
        except Exception as error:  # noqa: BLE001 — one corrupt file must never abort the whole run
            result.skipped.append((file_path, str(error)))
            if file_path.name in old_sections and file_path.name in old_hashes:
                # The file changed but re-extraction failed: keep the previous (stale)
                # section and its old hash so the aggregate doesn't silently lose the
                # document — the hash mismatch makes the next run retry extraction.
                sections.append(old_sections[file_path.name])
                ingested_files.append(file_path)
                current_hashes[file_path.name] = old_hashes[file_path.name]
            else:
                current_hashes.pop(file_path.name, None)
            if verbose:
                print(f"  Skipped {file_path}: {error}")
            continue

        if not verification.passed:
            result.flagged.append((file_path, verification.issue))
            if verbose:
                print(f"  Flagged {file_path}: {verification.issue}")
        sections.append(render_section(file_path, document, verification))
        if derive_per_file:
            write_facts_file(file_path, root, document)
        ingested_files.append(file_path)
        extracted_any = True
        current_hashes[file_path.name] = hash_file(file_path)  # OCR may have rewritten the PDF
        for tag in document.frontmatter.tags:
            if tag not in tags:
                tags.append(tag)

    if not ingested_files:
        return
    if not extracted_any and existing is not None and current_hashes == old_hashes:
        result.unchanged_dirs.append(directory)
        return

    relative_dir = directory.relative_to(root)
    frontmatter = OKFFrontmatter(
        type=FOLDER_SUMMARY_OKF_TYPE,
        title=directory.name.replace("_", " ").title(),
        description=f"Aggregated extraction of {len(ingested_files)} document(s) in {relative_dir or '.'}",
        tags=tags,
        source=None,
        sources=[str(f.relative_to(root)) for f in ingested_files],
        source_hashes=current_hashes,
    )
    joined_sections = "\n\n".join(sections)
    body = joined_sections
    try:
        orientation = client.summarize_sections(joined_sections)
    except LLMClientError as error:
        orientation = ""
        result.skipped.append((summary_path, f"orientation summary skipped: {error}"))
    if orientation:
        body = f"{orientation}\n\n{joined_sections}"
    summary = OKFDocument(frontmatter=frontmatter, body=body)
    summary_path.write_text(summary.to_markdown(), encoding="utf-8")
    result.written_paths.append(summary_path)
    if verbose:
        print(f"  -> Wrote {summary_path}")


def _folder_concept(directory: Path) -> OKFDocument | None:
    """Load a folder's own concept file if it is our output (a FolderSummary or FolderIndex)."""
    document = load_existing_summary(folder_summary_path(directory))
    if document is None or document.frontmatter.type not in {FOLDER_SUMMARY_OKF_TYPE, FOLDER_INDEX_OKF_TYPE}:
        return None
    return document


def _immediate_child_concepts(directory: Path) -> list[Path]:
    """Aggregate/index paths of the directory's immediate subfolders that have one."""
    children: list[Path] = []
    for sub in sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if _folder_concept(sub) is not None:
            children.append(folder_summary_path(sub))
    return children


def _build_rollup_section(directory: Path, child_paths: list[Path]) -> str:
    """Build the '## Subfolders' section: links to child aggregates, one line each.

    Finding-aid principle — the parent points down to each child with a short description
    drawn from the child's own frontmatter; it never inlines or re-summarizes the child's
    content. Links are relative to the parent aggregate's own location.
    """
    lines = [ROLLUP_HEADING, ""]
    for child_path in child_paths:
        child = _folder_concept(child_path.parent)
        description = ""
        if child is not None:
            description = child.frontmatter.description or child.frontmatter.title or ""
        relative_link = child_path.relative_to(directory).as_posix()
        label = child_path.parent.name
        lines.append(f"- [{label}]({relative_link})" + (f" — {description}" if description else ""))
    return "\n".join(lines)


def _inject_rollup(body: str, section: str) -> str:
    """Replace any existing roll-up section in a body with a fresh one appended at the end."""
    stripped = _ROLLUP_SECTION_PATTERN.sub("", body).rstrip()
    return f"{stripped}\n\n{section}" if stripped else section


def write_rollups(root: Path, result: IngestFolderResult, *, verbose: bool) -> None:
    """Give every non-root folder with subfolders a roll-up index into its children.

    Core behaviour (not a toggle): the archival hierarchy is only navigable if each level
    describes the level beneath it. A folder that has its own documents gets a roll-up
    section appended to its FolderSummary; a folder with only subfolders (no documents of
    its own) gets a lightweight FolderIndex file. Neither re-extracts or inlines child
    content, and files are only rewritten when their rendered text actually changes, so
    unchanged runs stay no-ops. Processed deepest-first so child indexes exist before a
    parent links them.
    """
    directories = sorted(
        (
            p
            for p in root.rglob("*")
            if p.is_dir() and not any(part.startswith(".") for part in p.relative_to(root).parts)
        ),
        key=lambda p: len(p.relative_to(root).parts),
        reverse=True,
    )
    for directory in directories:
        summary_path = folder_summary_path(directory)
        if summary_path.name in RESERVED_CONCEPT_FILENAMES:
            continue
        child_paths = _immediate_child_concepts(directory)
        existing = _folder_concept(directory)

        if not child_paths:
            # A former pure-parent whose children are all gone: drop its stale index.
            if existing is not None and existing.frontmatter.type == FOLDER_INDEX_OKF_TYPE:
                summary_path.unlink()
                result.removed_paths.append(summary_path)
            continue

        section = _build_rollup_section(directory, child_paths)
        if existing is not None and existing.frontmatter.type == FOLDER_SUMMARY_OKF_TYPE:
            document = existing.model_copy(update={"body": _inject_rollup(existing.body, section)})
        elif existing is not None and existing.frontmatter.type == FOLDER_INDEX_OKF_TYPE:
            # Reuse the existing index (preserving its timestamp) so an unchanged run is a
            # true no-op — recreating it would stamp a fresh datetime every time.
            document = existing.model_copy(update={"body": section})
        else:
            relative_dir = directory.relative_to(root)
            frontmatter = OKFFrontmatter(
                type=FOLDER_INDEX_OKF_TYPE,
                title=directory.name.replace("_", " ").title(),
                description=f"Index of {len(child_paths)} subfolder(s) in {relative_dir or '.'}",
                source=None,
            )
            document = OKFDocument(frontmatter=frontmatter, body=section)

        rendered = document.to_markdown()
        if summary_path.is_file() and summary_path.read_text(encoding="utf-8") == rendered:
            continue
        summary_path.write_text(rendered, encoding="utf-8")
        if summary_path not in result.written_paths:
            result.written_paths.append(summary_path)
        if verbose:
            print(f"  -> Roll-up {summary_path}")
