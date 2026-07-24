"""Cross-folder "dream" synthesis pass over the folder aggregates (the librarian).

Honcho-inspired in *shape* only: extraction happens at write time (ingest), and this
pass runs idle-time/cron-time over the accumulated aggregates to notice what no single
folder shows — the same matter spanning folders, contradictions, patterns, and open
actions. No queue, no database: input is the aggregates on disk, output is one
root-level `synthesis.md` (`type: Synthesis`).

Incremental like ingest: the synthesis stores a SHA-256 per source aggregate in its
frontmatter. When no aggregate changed since the last dream, the pass makes zero LLM
calls.

Two passes, bounded cost:

1. **Cheap scan** (`_synthesize`): one call (or a few, batched) over compact per-aggregate
   digests (identity, tags, orientation summary, section headings — not full bodies) across
   the *entire* tree. Produces a baseline four-section report. This alone is what shipped
   first; it is cheap because digests are small, but it cannot cite exact amounts/dates/IDs
   that only live in aggregate section bodies, which digests deliberately exclude.
2. **Deep dive** (`_deep_dive`): a non-LLM pre-filter (`app/services/matter_grouping.py`)
   groups aggregates that share a probable reference number (contract/customer/meter/case
   ID) — a purely local, free heuristic. Only those candidate *groups* get a follow-up call
   that reads their **full** aggregate text and produces a fact-dense Matter/Conflicts/Actions
   write-up. Cost scales with the number of candidate groups, not tree size. When a matter
   group exists, its deep-dive output replaces the cheap scan's Matters/Conflicts for that
   part of the report and its Actions merge in; Patterns always comes from the cheap scan
   (cross-cutting trends don't need forensic-level facts). When no groups are found, output
   is identical to the cheap-scan-only baseline — no regression, no extra cost.

Each deep-dived group is also persisted as its own concept file under `<root>/matters/`
(R2, `app/services/matter_files.py`, `type: Matter`) — a stable, linkable file per matter
rather than only a paragraph inside whatever `synthesis.md` happens to be current.
Hash-incremental per matter: a group whose own aggregates are unchanged reuses its existing
matter file instead of re-running the deep-dive call, even when an unrelated aggregate
elsewhere triggered this dream run.
"""

import re
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
from app.services.gating import GatingRules, is_deprioritized
from app.services.ingest import hash_file, load_existing_summary
from app.services.llm_client import LLMClient
from app.services.matter_files import (
    group_source_hashes,
    load_matter_body,
    matter_path,
    matter_unchanged,
    write_matter_file,
)
from app.services.matter_grouping import group_by_shared_tokens, group_tokens, min_token_digits_for_principle

DREAM_MAX_TOKENS = 4096
"""Synthesis is longer-form than per-document extraction; give it more output room."""

_SYNTHESIS_HEADERS = ("Matters", "Conflicts", "Patterns", "Open actions")
_SYNTHESIS_SECTION_PATTERN = re.compile(r"^##\s+(" + "|".join(_SYNTHESIS_HEADERS) + r")\s*$", re.MULTILINE)
_MATTER_SECTION_PATTERN = re.compile(r"^###\s+(Matter|Conflicts|Actions)\s*$", re.IGNORECASE | re.MULTILINE)
_NO_CONFLICTS_MARKERS = ("keine konflikte erkannt", "no conflicts detected")


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
    rules: GatingRules | None = None,
    ordering_principle: str = "provenance",
) -> DreamResult:
    """Run one dream pass over root's aggregates, writing/refreshing `<root>/synthesis.md`.

    Skips the LLM entirely when no aggregate changed since the last synthesis (unless
    `force`). Oversized digests are synthesized in batches, then consolidated with one
    final call over the partial syntheses.

    `rules` deprioritizes low-value aggregates (manuals, terms, user low-priority patterns)
    out of this expensive pass — they were still ingested, just not deeply analyzed.
    `ordering_principle` tunes how loosely cross-folder matters form (`pertinence` = looser).
    """
    root = Path(root_folder).expanduser().resolve()
    result = DreamResult(root=root)
    if not root.is_dir():
        result.errors.append(f"{root} is not a directory")
        return result

    gating_rules = rules or GatingRules()
    output_path = synthesis_path(root)
    aggregates = [
        path
        for path in collect_aggregates(root)
        if path != output_path and not is_deprioritized(str(path.parent.relative_to(root)), gating_rules)
    ]
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

    digest_map = {path: digest for path in aggregates if (digest := build_digest(path, root))}
    if verbose:
        print(f"Dreaming over {len(digest_map)} aggregate(s)...")

    llm_client = client or LLMClient(log_path=root / LLM_LOG_FILENAME)
    try:
        baseline_body = _synthesize(list(digest_map.values()), llm_client)
        groups = group_by_shared_tokens(digest_map, min_digits=min_token_digits_for_principle(ordering_principle))
        if verbose and groups:
            print(f"  {len(groups)} candidate matter group(s) found — deep-diving...")
        body = _apply_deep_dives(baseline_body, groups, digest_map, root, llm_client, verbose=verbose)
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


def _apply_deep_dives(
    baseline_body: str,
    groups: list[list[Path]],
    digest_map: dict[Path, str],
    root: Path,
    client: LLMClient,
    *,
    verbose: bool,
) -> str:
    """Splice deep-dive Matter/Conflicts/Actions into the cheap-scan baseline report.

    Also persists each group's write-up as its own concept file under `<root>/matters/`
    (R2, `app/services/matter_files.py`) and, per group, skips the deep-dive LLM call
    entirely when that group's own source hashes already match its existing matter file —
    hash-incremental per matter, not just per whole-tree synthesis.

    Patterns always comes from the baseline (cross-cutting trends don't need per-fact
    depth). If the baseline didn't parse into recognizable sections at all (a small model
    deviated from the format), skip splicing entirely rather than risk losing content —
    the baseline body ships as-is, same as before this feature existed.
    """
    if not groups:
        return baseline_body

    sections = _split_sections(baseline_body)
    if not any(sections.values()):
        return baseline_body

    matter_blocks: list[str] = []
    conflict_blocks: list[str] = []
    action_blocks: list[str] = []
    for group in groups:
        tokens = group_tokens(group, digest_map)
        current_hashes = group_source_hashes(group, root)
        existing_path = matter_path(root, tokens, group)
        if matter_unchanged(existing_path, current_hashes):
            if verbose:
                print(f"    Matter unchanged, reusing: {existing_path.relative_to(root)}")
            raw = load_matter_body(existing_path) or ""
        else:
            if verbose:
                print(f"    Deep dive: {', '.join(str(p.relative_to(root)) for p in group)}")
            raw = _deep_dive(group, root, client)
            write_matter_file(root, group, tokens, raw)
        matter, conflicts, actions = _parse_matter_sections(raw)
        if matter:
            matter_blocks.append(matter)
        if conflicts and conflicts.strip().lower() not in _NO_CONFLICTS_MARKERS:
            conflict_blocks.append(conflicts)
        if actions:
            action_blocks.append(actions)

    if matter_blocks:
        sections["Matters"] = "\n\n".join(matter_blocks)
    if conflict_blocks:
        sections["Conflicts"] = "\n\n".join(conflict_blocks)
    if action_blocks:
        existing_actions = sections.get("Open actions", "")
        sections["Open actions"] = "\n\n".join(filter(None, [existing_actions, *action_blocks]))

    return _join_sections(sections)


def _deep_dive(group: list[Path], root: Path, client: LLMClient) -> str:
    """Run one matter deep-dive over a candidate group's full aggregate text.

    Batches + consolidates like `_synthesize` when the group's combined text exceeds the
    character budget — rare, most matters span a handful of files, but a real dispute can
    easily involve a dozen+ documents across several folders.
    """
    parts = [f"=== {path.relative_to(root)} ===\n{path.read_text(encoding='utf-8')}" for path in group]
    batches = _batch_digests(parts, CHUNK_CHAR_THRESHOLD)
    if len(batches) == 1:
        return client.dream_matter(batches[0], max_tokens=DREAM_MAX_TOKENS)

    partials = [
        client.dream_matter(
            f"(Partial evidence {i + 1}/{len(batches)} for this candidate matter.)\n\n{batch}",
            max_tokens=DREAM_MAX_TOKENS,
        )
        for i, batch in enumerate(batches)
    ]
    consolidation_input = "\n\n---\n\n".join(
        f"(Partial write-up {i + 1}/{len(partials)})\n\n{partial}" for i, partial in enumerate(partials)
    )
    return client.dream_matter(
        "The following are partial Matter/Conflicts/Actions write-ups for the SAME candidate "
        "matter, each from a different subset of its evidence. Merge them into one coherent "
        f"set of three sections, deduplicating repeated facts.\n\n{consolidation_input}",
        max_tokens=DREAM_MAX_TOKENS,
    )


def _parse_matter_sections(text: str) -> tuple[str, str, str]:
    """Split a deep-dive response into (matter, conflicts, actions).

    Tolerant of missing/malformed headers (small local models aren't always reliable) —
    everything falls into `matter` rather than being silently dropped.
    """
    matches = list(_MATTER_SECTION_PATTERN.finditer(text))
    if not matches:
        return text.strip(), "", ""
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match.group(1).lower()] = text[start:end].strip()
    return sections.get("matter", ""), sections.get("conflicts", ""), sections.get("actions", "")


def _split_sections(body: str) -> dict[str, str]:
    """Split a synthesis body into its four named sections (empty string if absent)."""
    matches = list(_SYNTHESIS_SECTION_PATTERN.finditer(body))
    sections = dict.fromkeys(_SYNTHESIS_HEADERS, "")
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[start:end].strip()
    return sections


def _join_sections(sections: dict[str, str]) -> str:
    """Reassemble a sections dict back into one markdown body, dropping empty sections."""
    return "\n\n".join(f"## {header}\n\n{sections[header]}" for header in _SYNTHESIS_HEADERS if sections[header])
