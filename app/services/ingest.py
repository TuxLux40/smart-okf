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
    FOLDER_SUMMARY_OKF_TYPE,
    LLM_LOG_FILENAME,
    RESERVED_CONCEPT_FILENAMES,
    TRANSCRIPTS_DIR_NAME,
)
from app.exceptions import DocumentIngestError, LLMClientError
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.chunking import chunk_text
from app.services.llm_client import LLMClient
from app.services.text_extraction import extract_text_from_file, is_supported_document
from app.types import FrontmatterPatch

_SOURCE_MARKER_PATTERN = re.compile(r"^_Source: (?P<name>.+)_$", re.MULTILINE)


@dataclass
class IngestFolderResult:
    """Summary of a folder ingest run."""

    root: Path
    written_paths: list[Path] = field(default_factory=list)
    unchanged_dirs: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Return a process exit code for CLI callers."""
        if not self.root.is_dir():
            return 1
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


def extract_document(file_path: Path, root: Path, client: LLMClient, *, use_marker: bool = False) -> OKFDocument:
    """Extract and structure one document into an OKF document (no aggregate write).

    Documents too large for a single LLM call are chunked (`chunk_text`) and extracted
    per chunk, then merged (`merge_chunk_documents`) — this always returns exactly one
    document, preserving the one-file-one-aggregate-section invariant regardless of how
    many LLM calls it took.
    """
    raw_text = extract_text_from_file(file_path, use_marker=use_marker)
    if not raw_text.strip():
        raise DocumentIngestError(f"No extractable text in {file_path}")
    write_transcript(file_path, root, raw_text)

    context = str(file_path.relative_to(root))
    chunks = chunk_text(raw_text)
    documents: list[OKFDocument] = []
    for i, chunk in enumerate(chunks):
        chunk_context = context if len(chunks) == 1 else f"{context} (part {i + 1}/{len(chunks)})"
        extracted_markdown = client.extract_structured(chunk, context=chunk_context)
        try:
            documents.append(OKFDocument.from_markdown(extracted_markdown))
        except Exception as error:
            raise DocumentIngestError(f"Failed to parse OKF markdown for {file_path}") from error

    document = merge_chunk_documents(documents) if len(documents) > 1 else documents[0]
    return apply_ingest_defaults(document, file_path, root)


def merge_chunk_documents(documents: list[OKFDocument]) -> OKFDocument:
    """Merge multiple chunk-extracted documents (one file, split across LLM calls) into one.

    Frontmatter identity (type/title/description/timestamp/source) comes from the first
    chunk, which usually contains the letterhead/subject line; tags union across chunks.
    """
    tags: list[str] = []
    for document in documents:
        for tag in document.frontmatter.tags:
            if tag not in tags:
                tags.append(tag)
    frontmatter = documents[0].frontmatter.model_copy(update={"tags": tags})
    body = "\n\n".join(document.body for document in documents)
    return OKFDocument(frontmatter=frontmatter, body=body)


def render_section(file_path: Path, document: OKFDocument) -> str:
    """Render one source document's body section for the folder aggregate.

    Headings inside the document body are demoted one level (capped at h6) so the
    aggregate's `## <document>` sections stay the only h2s — `parse_existing_sections`
    splits on h2, and un-demoted inner h2s would fragment a section and silently
    truncate it on incremental re-ingest.
    """
    heading = document.frontmatter.title or file_path.name
    body = re.sub(r"^(#{1,5}) ", r"#\1 ", document.body, flags=re.MULTILINE)
    return f"## {heading}\n\n_Source: {file_path.name}_\n\n{body}"


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


def ingest_folder(
    folder: str,
    client: LLMClient | None = None,
    *,
    use_marker: bool = False,
    verbose: bool = False,
) -> IngestFolderResult:
    """Ingest supported documents from a folder, writing one aggregate `.md` per subfolder."""
    root = Path(folder).expanduser().resolve()
    result = IngestFolderResult(root=root)
    if not root.is_dir():
        if verbose:
            print(f"Error: {root} is not a directory")
        return result

    llm_client = client or LLMClient(log_path=root / LLM_LOG_FILENAME)
    if verbose:
        print(f"Scanning {root}...")

    directories = [root] + sorted(
        p for p in root.rglob("*") if p.is_dir() and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )
    for directory in directories:
        _ingest_directory(directory, root, llm_client, result, use_marker=use_marker, verbose=verbose)

    if verbose:
        print(
            f"Ingest complete. Wrote {len(result.written_paths)} aggregate(s), "
            f"{len(result.unchanged_dirs)} folder(s) unchanged."
        )

    return result


def _ingest_directory(
    directory: Path,
    root: Path,
    client: LLMClient,
    result: IngestFolderResult,
    *,
    use_marker: bool = False,
    verbose: bool,
) -> None:
    """Ingest the files directly inside one directory (non-recursive) into its aggregate."""
    files = sorted(f for f in directory.iterdir() if f.is_file() and is_supported_document(f))
    if not files:
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
            if not transcript_path(file_path, root).exists():
                with contextlib.suppress(DocumentIngestError):
                    write_transcript(file_path, root, extract_text_from_file(file_path, use_marker=use_marker))
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
            if not transcript_path(file_path, root).exists():
                # Backfill: local re-extraction is LLM-free, so a missing transcript
                # (files ingested before the transcript store existed) is cheap to fix.
                with contextlib.suppress(DocumentIngestError):
                    write_transcript(file_path, root, extract_text_from_file(file_path, use_marker=use_marker))
            continue

        if verbose:
            print(f"Processing: {file_path}")
        try:
            document = extract_document(file_path, root, client, use_marker=use_marker)
        except (DocumentIngestError, LLMClientError) as error:
            result.skipped.append((file_path, str(error)))
            current_hashes.pop(file_path.name, None)
            if verbose:
                print(f"  Skipped {file_path}: {error}")
            continue

        sections.append(render_section(file_path, document))
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
