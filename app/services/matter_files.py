"""Per-matter concept files (R2): one dedicated, hash-incremental `.md` per cross-folder
matter group, alongside the whole-tree `synthesis.md` (R2b).

`app/services/dream.py`'s deep dive already reads a candidate group's full aggregate text
and produces a Matter/Conflicts/Actions write-up; this module persists that write-up as its
own concept file under `<root>/matters/`, `type: Matter`, instead of only splicing it into
the synthesis. Two things follow from making it a real file:

- **Findable independent of a fresh dream run.** `synthesis.md` is regenerated wholesale
  each time; a matter file is a stable, linkable concept an agent (or a git history search)
  can point at directly — "the ACME-Energy dispute" instead of "some paragraph in whichever
  synthesis.md happened to be current."
- **Hash-incremental per matter, not just per synthesis.** The synthesis's own incremental
  gate is whole-tree: any changed aggregate anywhere reruns every deep dive. Persisting each
  matter's source hashes lets `dream()` skip the (expensive, full-text) deep-dive call for
  groups whose own aggregates are unchanged, even when an unrelated aggregate elsewhere
  triggered the run.
"""

import hashlib
from pathlib import Path

from app.constants import MATTER_OKF_TYPE, MATTERS_DIR_NAME
from app.models.okf import OKFDocument, OKFFrontmatter
from app.services.ingest import hash_file, load_existing_summary

_FALLBACK_SLUG_LENGTH = 12


def matter_slug(tokens: list[str], group: list[Path]) -> str:
    """Stable filename stem for a matter group.

    Prefers the shared reference number(s) (human-legible, stable across reruns as long as
    the same aggregates keep sharing the same token). Falls back to a short hash of the
    member paths only if a group somehow carries no shared token (shouldn't happen — groups
    are formed *by* shared tokens — but this keeps naming total rather than partial).
    """
    if tokens:
        return "matter-" + "-".join(tokens[:3])
    digest = hashlib.sha256("|".join(sorted(str(path) for path in group)).encode("utf-8")).hexdigest()
    return "matter-" + digest[:_FALLBACK_SLUG_LENGTH]


def matter_path(root: Path, tokens: list[str], group: list[Path]) -> Path:
    """Return `<root>/matters/<slug>.md` for this group."""
    return root / MATTERS_DIR_NAME / f"{matter_slug(tokens, group)}.md"


def group_source_hashes(group: list[Path], root: Path) -> dict[str, str]:
    """SHA-256 per group member, keyed by its path relative to root — mirrors ingest/dream."""
    return {str(path.relative_to(root)): hash_file(path) for path in group}


def matter_unchanged(path: Path, current_hashes: dict[str, str]) -> bool:
    """True if a matter file already exists at `path` with matching source hashes."""
    existing = load_existing_summary(path)
    return (
        existing is not None
        and existing.frontmatter.type == MATTER_OKF_TYPE
        and existing.frontmatter.source_hashes == current_hashes
    )


def load_matter_body(path: Path) -> str | None:
    """Return a previously written matter file's body, or None if absent/unreadable."""
    existing = load_existing_summary(path)
    return existing.body if existing is not None else None


def write_matter_file(root: Path, group: list[Path], tokens: list[str], deep_dive_raw: str) -> Path:
    """Write/update `<root>/matters/<slug>.md` with the deep dive's raw section text.

    The body keeps the deep dive's own `### Matter` / `### Conflicts` / `### Actions`
    headings verbatim (prefixed by a plain aggregate-links list) so a later unchanged-run
    can feed the stored body straight back through `dream._parse_matter_sections` without
    needing a second, file-specific parser.
    """
    path = matter_path(root, tokens, group)
    current_hashes = group_source_hashes(group, root)
    links = "\n".join(f"- [{rel}](../{rel})" for rel in sorted(current_hashes))
    body = f"## Involved aggregates\n\n{links}\n\n{deep_dive_raw.strip()}"
    label = ", ".join(tokens) if tokens else matter_slug(tokens, group)
    frontmatter = OKFFrontmatter(
        type=MATTER_OKF_TYPE,
        title=f"Matter {label}",
        description=f"Cross-folder matter linking {len(group)} aggregate(s) sharing reference {label}",
        tags=list(tokens),
        source=None,
        sources=sorted(current_hashes),
        source_hashes=current_hashes,
    )
    document = OKFDocument(frontmatter=frontmatter, body=body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.to_markdown(), encoding="utf-8")
    return path
