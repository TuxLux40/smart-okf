"""Document ingest helpers shared by CLI and UI."""

from dataclasses import dataclass, field
from pathlib import Path

from app.exceptions import DocumentIngestError, LLMClientError
from app.models.okf import OKFDocument
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


def co_located_markdown_path(file_path: Path) -> Path:
    """Return the companion markdown path for an original document."""
    return file_path.with_suffix(".md")


def ingest_document_file(
    file_path: Path,
    root: Path,
    client: LLMClient,
) -> Path:
    """Extract, structure, and write one co-located OKF markdown file."""
    raw_text = extract_text_from_file(file_path)
    if not raw_text.strip():
        raise DocumentIngestError(f"No extractable text in {file_path}")

    extracted_markdown = client.extract_structured(
        raw_text,
        context=str(file_path.relative_to(root)),
    )

    try:
        document = OKFDocument.from_markdown(extracted_markdown)
        document = apply_ingest_defaults(document, file_path, root)
        markdown_path = co_located_markdown_path(file_path)
        markdown_path.parent.mkdir(exist_ok=True)
        markdown_path.write_text(document.to_markdown(), encoding="utf-8")
    except DocumentIngestError:
        raise
    except Exception as error:
        raise DocumentIngestError(f"Failed to write OKF markdown for {file_path}") from error

    return markdown_path


def ingest_folder(
    folder: str,
    client: LLMClient | None = None,
    *,
    verbose: bool = False,
) -> IngestFolderResult:
    """Ingest supported documents from a folder."""
    root = Path(folder).expanduser().resolve()
    result = IngestFolderResult(root=root)
    if not root.is_dir():
        if verbose:
            print(f"Error: {root} is not a directory")
        return result

    llm_client = client or LLMClient()
    if verbose:
        print(f"Scanning {root}...")

    for file_path in root.rglob("*"):
        if not file_path.is_file() or not is_supported_document(file_path):
            continue

        if verbose:
            print(f"Processing: {file_path}")

        try:
            markdown_path = ingest_document_file(file_path, root, llm_client)
        except DocumentIngestError as error:
            result.skipped.append((file_path, str(error)))
            if verbose:
                print(f"  Skipped {file_path}: {error}")
            continue
        except LLMClientError as error:
            result.skipped.append((file_path, str(error)))
            if verbose:
                print(f"  LLM failed for {file_path}: {error}")
            continue

        result.written_paths.append(markdown_path)
        if verbose:
            print(f"  -> Wrote {markdown_path}")

    if verbose:
        print(f"Ingest complete. Wrote {len(result.written_paths)} markdown file(s).")

    return result
