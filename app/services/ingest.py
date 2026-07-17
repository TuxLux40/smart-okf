"""Document ingest helpers shared by CLI and UI.

Writes one aggregate OKF markdown file per folder (non-recursive: a folder's aggregate
covers only the files directly inside it, not files in subfolders) rather than one
companion per source document, to keep folders with many documents from becoming
cluttered with individual `.md` files.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.constants import FOLDER_SUMMARY_OKF_TYPE, RESERVED_CONCEPT_FILENAMES
from app.exceptions import DocumentIngestError, LLMClientError
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.llm_client import LLMClient
from app.services.text_extraction import extract_text_from_file, is_supported_document
from app.types import FrontmatterPatch


@dataclass
class IngestFolderResult:
    """Summary of a folder ingest run."""

    root: Path
    written_paths: list[Path] = field(default_factory=list)
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


def extract_document(file_path: Path, root: Path, client: LLMClient) -> OKFDocument:
    """Extract and structure one document into an OKF document (no write)."""
    raw_text = extract_text_from_file(file_path)
    if not raw_text.strip():
        raise DocumentIngestError(f"No extractable text in {file_path}")

    extracted_markdown = client.extract_structured(
        raw_text,
        context=str(file_path.relative_to(root)),
    )
    try:
        document = OKFDocument.from_markdown(extracted_markdown)
    except Exception as error:
        raise DocumentIngestError(f"Failed to parse OKF markdown for {file_path}") from error
    return apply_ingest_defaults(document, file_path, root)


def build_folder_summary(
    directory: Path,
    root: Path,
    documents: list[tuple[Path, OKFDocument]],
) -> OKFDocument:
    """Merge per-file extractions into one folder-level aggregate OKF document."""
    tags: list[str] = []
    for _, document in documents:
        for tag in document.frontmatter.tags:
            if tag not in tags:
                tags.append(tag)

    sources = [str(file_path.relative_to(root)) for file_path, _ in documents]
    relative_dir = directory.relative_to(root)
    frontmatter = OKFFrontmatter(
        type=FOLDER_SUMMARY_OKF_TYPE,
        title=directory.name.replace("_", " ").title(),
        description=f"Aggregated extraction of {len(documents)} document(s) in {relative_dir or '.'}",
        tags=tags,
        source=None,
        sources=sources,
    )

    sections = []
    for file_path, document in documents:
        heading = document.frontmatter.title or file_path.name
        sections.append(f"## {heading}\n\n_Source: {file_path.name}_\n\n{document.body}")
    body = "\n\n".join(sections)

    return OKFDocument(frontmatter=frontmatter, body=body)


def ingest_folder(
    folder: str,
    client: LLMClient | None = None,
    *,
    verbose: bool = False,
) -> IngestFolderResult:
    """Ingest supported documents from a folder, writing one aggregate `.md` per subfolder."""
    root = Path(folder).expanduser().resolve()
    result = IngestFolderResult(root=root)
    if not root.is_dir():
        if verbose:
            print(f"Error: {root} is not a directory")
        return result

    llm_client = client or LLMClient()
    if verbose:
        print(f"Scanning {root}...")

    directories = [root] + sorted(p for p in root.rglob("*") if p.is_dir())
    for directory in directories:
        _ingest_directory(directory, root, llm_client, result, verbose=verbose)

    if verbose:
        print(f"Ingest complete. Wrote {len(result.written_paths)} folder summary file(s).")

    return result


def _ingest_directory(
    directory: Path,
    root: Path,
    client: LLMClient,
    result: IngestFolderResult,
    *,
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

    documents: list[tuple[Path, OKFDocument]] = []
    for file_path in files:
        if verbose:
            print(f"Processing: {file_path}")
        try:
            documents.append((file_path, extract_document(file_path, root, client)))
        except DocumentIngestError as error:
            result.skipped.append((file_path, str(error)))
            if verbose:
                print(f"  Skipped {file_path}: {error}")
        except LLMClientError as error:
            result.skipped.append((file_path, str(error)))
            if verbose:
                print(f"  LLM failed for {file_path}: {error}")

    if not documents:
        return

    summary = build_folder_summary(directory, root, documents)
    summary_path.write_text(summary.to_markdown(), encoding="utf-8")
    result.written_paths.append(summary_path)
    if verbose:
        print(f"  -> Wrote {summary_path}")
