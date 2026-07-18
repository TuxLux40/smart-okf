"""Cross-folder "dream" synthesis pass over the folder aggregates (the librarian).

Honcho-inspired in *shape* only: extraction happens at write time (ingest), and this
pass runs idle-time/cron-time over the accumulated aggregates to notice what no single
folder shows — the same matter spanning folders, contradictions, patterns, and open
actions. No queue, no database: input is the aggregates on disk, output is one
root-level `synthesis.md` (`type: Synthesis`).

Incremental like ingest: the synthesis stores a SHA-256 per source aggregate in its
frontmatter. When no aggregate changed since the last dream, the pass makes zero LLM
calls. The digest fed to the model is deliberately compact (frontmatter identity +
orientation summary + section headings), not full aggregate bodies — the aggregates
already are the distilled form; dreaming reasons across them, it does not re-read
everything.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.constants import (
    CHUNK_CHAR_THRESHOLD,
    FOLDER_SUMMARY_OKF_TYPE,
    LLM_LOG_FILENAME,
    SYNTHESIS_FILENAME,
    SYNTHESIS_OKF_TYPE,
)
from app.exceptions import LLMClientError
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.ingest import hash_file, load_existing_summary
from app.services.llm_client import LLMClient

DREAM_MAX_TOKENS = 4096
"""Synthesis is longer-form than per-document extraction; give it more output room."""


@dataclass
class DreamResult:
    """Summary of a dream pass."""

    root: Path
    synthesis_path: Path | None = None
    aggregate_count: int = 0
    unchanged: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Process exit code for CLI callers: 1 on errors, 0 otherwise (unchanged is fine)."""
        return 1 if self.errors else 0


def synthesis_path(root: Path) -> Path:
    """Return the root-level synthesis output path."""
    return root / SYNTHESIS_FILENAME


def collect_aggregates(root: Path) -> list[Path]:
    """Find every folder aggregate (`type: FolderSummary`) under root, hidden dirs excluded."""
    aggregates: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        document = load_existing_summary(path)
        if document is not None and document.frontmatter.type == FOLDER_SUMMARY_OKF_TYPE:
            aggregates.append(path)
    return aggregates


def build_digest(aggregate_path: Path, root: Path) -> str:
    """Compact digest of one aggregate: identity, tags, orientation summary, section headings.

    Full bodies stay out — they would blow the context budget on real trees, and the
    orientation summary + headings + source list carry the joinable facts (IDs live in
    headings/summaries/tags after extraction).
    """
    document = load_existing_summary(aggregate_path)
    if document is None:
        return ""
    relative = aggregate_path.relative_to(root)
    lines = [f"### Aggregate: {relative}"]
    if document.frontmatter.title:
        lines.append(f"Title: {document.frontmatter.title}")
    if document.frontmatter.tags:
        lines.append(f"Tags: {', '.join(document.frontmatter.tags)}")
    if document.frontmatter.sources:
        lines.append(f"Sources: {', '.join(document.frontmatter.sources)}")

    body = document.body.strip()
    first_section = body.find("## ")
    orientation = body[:first_section].strip() if first_section > 0 else ""
    if orientation:
        lines.append(f"Summary: {orientation}")
    headings = [line for line in body.splitlines() if line.startswith("## ") or line.startswith("_Source: ")]
    if headings:
        lines.append("Sections:")
        lines.extend(f"  {heading}" for heading in headings)
    return "\n".join(lines)


def dream(
    root_folder: str,
    client: LLMClient | None = None,
    *,
    force: bool = False,
    verbose: bool = False,
) -> DreamResult:
    """Run one dream pass over root's aggregates, writing/refreshing `<root>/synthesis.md`.

    Skips the LLM entirely when no aggregate changed since the last synthesis (unless
    `force`). Oversized digests are synthesized in batches, then consolidated with one
    final call over the partial syntheses.
    """
    root = Path(root_folder).expanduser().resolve()
    result = DreamResult(root=root)
    if not root.is_dir():
        result.errors.append(f"{root} is not a directory")
        return result

    output_path = synthesis_path(root)
    aggregates = [path for path in collect_aggregates(root) if path != output_path]
    result.aggregate_count = len(aggregates)
    if not aggregates:
        result.errors.append(f"no folder aggregates found under {root}; run ingest first")
        return result

    current_hashes = {str(path.relative_to(root)): hash_file(path) for path in aggregates}
    existing = load_existing_summary(output_path)
    if (
        not force
        and existing is not None
        and existing.frontmatter.type == SYNTHESIS_OKF_TYPE
        and existing.frontmatter.source_hashes == current_hashes
    ):
        result.unchanged = True
        result.synthesis_path = output_path
        if verbose:
            print(f"Unchanged: no aggregate changed since last dream ({output_path})")
        return result

    digests = [digest for path in aggregates if (digest := build_digest(path, root))]
    if verbose:
        print(f"Dreaming over {len(digests)} aggregate(s)...")

    llm_client = client or LLMClient(log_path=root / LLM_LOG_FILENAME)
    try:
        body = _synthesize(digests, llm_client)
    except LLMClientError as error:
        result.errors.append(f"dream synthesis failed: {error}")
        return result

    frontmatter = OKFFrontmatter(
        type=SYNTHESIS_OKF_TYPE,
        title="Cross-folder synthesis",
        description=f"Dream pass over {len(aggregates)} folder aggregate(s): matters, conflicts, patterns, actions",
        source=None,
        sources=sorted(current_hashes),
        source_hashes=current_hashes,
    )
    document = OKFDocument(frontmatter=frontmatter, body=body)
    output_path.write_text(document.to_markdown(), encoding="utf-8")
    result.synthesis_path = output_path
    if verbose:
        print(f"  -> Wrote {output_path}")
    return result


def _synthesize(digests: list[str], client: LLMClient) -> str:
    """One dream call, or batched calls + a consolidation call when the digest is oversized."""
    batches = _batch_digests(digests, CHUNK_CHAR_THRESHOLD)
    if len(batches) == 1:
        return client.dream_synthesis(batches[0], max_tokens=DREAM_MAX_TOKENS)

    partials = [
        client.dream_synthesis(
            f"(Partial digest {i + 1}/{len(batches)} — synthesize what this subset shows.)\n\n{batch}",
            max_tokens=DREAM_MAX_TOKENS,
        )
        for i, batch in enumerate(batches)
    ]
    consolidation_input = "\n\n---\n\n".join(
        f"(Partial synthesis {i + 1}/{len(partials)})\n\n{partial}" for i, partial in enumerate(partials)
    )
    return client.dream_synthesis(
        "The following are partial syntheses of subsets of the knowledge base. Merge them into "
        "one consistent report with the same four sections, deduplicating matters that appear "
        f"in several partials.\n\n{consolidation_input}",
        max_tokens=DREAM_MAX_TOKENS,
    )


def _batch_digests(digests: list[str], budget: int) -> list[str]:
    """Group per-aggregate digests into batches under the character budget.

    A single digest larger than the budget becomes its own batch — digests are compact
    by construction, so this is a safety valve, not an expected path.
    """
    batches: list[str] = []
    current: list[str] = []
    current_size = 0
    for digest in digests:
        addition = len(digest) + 2
        if current and current_size + addition > budget:
            batches.append("\n\n".join(current))
            current = []
            current_size = 0
        current.append(digest)
        current_size += addition
    if current:
        batches.append("\n\n".join(current))
    return batches
