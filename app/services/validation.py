"""Heuristic plausibility checks for OKF aggregate/matter documents.

Not an LLM judge, not a fact-checker — deliberately not "have a second model grade
the first one," which would double the token/time cost of every ingest run for a
correctness check that still can't verify facts without the source and a human
anyway. Instead: cheap, deterministic checks for the *shapes* two real failures
took in this project. Neither needed a second model call to catch:

- A large batch of aggregates that were empty templated placeholders — the model
  never actually read the source files (`sources: is non-empty`, the citation
  check, and the density check below).
- A weak local model degenerating into a repetition loop and echoing its own
  extraction-prompt template verbatim instead of filling it in (the leaked-
  frontmatter, template-placeholder, repeated-block, and meta-commentary checks
  below) — caught from the *structure* of the failure (a nested frontmatter block,
  a literal `path/to/...`, the same paragraph six times with only the timestamp
  changing), not by judging whether the content is factually correct.

A failed check is a prompt to look, not proof of a problem — a genuinely tiny folder
can have little to say about one short document, and none of this substitutes for a
human occasionally reading the actual aggregate. Modeled on skill-creator's
eval-assertion shape (`text`/`passed`/`evidence` per check): verify programmatically
what's objectively checkable, leave judgment calls to a human.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.constants import FOLDER_SUMMARY_OKF_TYPE, MATTER_OKF_TYPE
from app.models.okf import OKFDocument
from app.services.ingest import _SOURCE_MARKER_PATTERN, load_existing_summary

MIN_BODY_CHARS_PER_SOURCE = 80
"""Below this per-source average, a body reads as a one-line placeholder rather than
a real extraction. Calibrated against real fabricated aggregates that triggered this
check (~20-30 body chars per source, one generic sentence regardless of source count)
against real ones (hundreds of chars per source, one section per document)."""

VALIDATABLE_OKF_TYPES = frozenset({FOLDER_SUMMARY_OKF_TYPE, MATTER_OKF_TYPE})
"""Document types this module knows how to check — both cite `sources:` against a
per-document `_Source:` line, so the same assertions apply to either."""

_LEAKED_FRONTMATTER_PATTERN = re.compile(r"^type:\s*\S+\s*$", re.MULTILINE)
"""A bare `type: <value>` line inside the body (the document's own frontmatter is
already stripped before the body reaches here) means the model pasted a nested OKF
frontmatter block from its own extraction template instead of merging it into prose
— observed verbatim in a real failure (fenced ```` ```markdown\\n---\\ntype: Fact\\n...
````` blocks inside a FolderSummary body)."""

_TEMPLATE_PLACEHOLDER_PATTERN = re.compile(
    r"^\s*(title|description|tags|source|timestamp):\s*(\.\.\.|\[\.\.\.\]|path/to/)",
    re.IGNORECASE | re.MULTILINE,
)
"""A literal `key: ...` or `source: path/to/...` line is the model echoing its own
prompt template's placeholder syntax verbatim rather than filling in a real value —
also observed verbatim in the same failure."""

_META_COMMENTARY_PHRASES = (
    "here is the output",
    "here's the output",
    "in valid okf",
    "as an ai",
    "focus on quality over quantity",
)
"""Known telltale phrases from a model replying to the extraction prompt as a chat
turn instead of writing a document. Not exhaustive by design — a denylist can only
ever cover phrases already seen; extend it when a new failure surfaces a new one,
don't expect it to catch every future case."""

MAX_REPEATED_BLOCK_OCCURRENCES = 2
"""A paragraph-sized block (40+ normalized characters, digits collapsed so a block
that only differs by an incrementing timestamp still counts as "the same block")
appearing more than this many times is very unlikely to be genuine per-document
content — real aggregates cite each source once. Flags a degenerate repetition
loop, the exact shape a real failure took (the same fact restated a dozen times
with only the timestamp changing until the model hit its token limit)."""

_DIGIT_PATTERN = re.compile(r"\d")


def _normalize_block_for_repetition(block: str) -> str:
    """Collapse whitespace and digits so near-duplicate blocks compare equal."""
    return _DIGIT_PATTERN.sub("#", " ".join(block.split()))


def _find_repeated_blocks(body: str) -> list[tuple[str, int]]:
    """Paragraph-sized blocks (blank-line separated) repeated past the threshold."""
    counts: dict[str, int] = {}
    for block in re.split(r"\n\s*\n", body):
        normalized = _normalize_block_for_repetition(block)
        if len(normalized) < 40:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    return [(block, count) for block, count in counts.items() if count > MAX_REPEATED_BLOCK_OCCURRENCES]


@dataclass
class ValidationFinding:
    """One assertion's result against a single document."""

    text: str
    passed: bool
    evidence: str = ""


@dataclass
class ValidationReport:
    """All findings for one document."""

    path: Path
    findings: list[ValidationFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True only if every finding passed."""
        return all(finding.passed for finding in self.findings)

    @property
    def failures(self) -> list[ValidationFinding]:
        """Findings that failed, for a short report instead of the full list."""
        return [finding for finding in self.findings if not finding.passed]


def validate_aggregate(document: OKFDocument, path: Path) -> ValidationReport:
    """Run heuristic plausibility checks against one FolderSummary/Matter document."""
    findings: list[ValidationFinding] = []
    sources = document.frontmatter.sources
    body = document.body.strip()

    findings.append(
        ValidationFinding(
            text="sources: is non-empty",
            passed=bool(sources),
            evidence=(f"{len(sources)} source(s) listed" if sources else "sources: [] — nothing was actually read"),
        )
    )

    if document.frontmatter.type == MATTER_OKF_TYPE:
        # Matter files don't use the `_Source:` marker convention at all — they cite
        # via free-form prose ("Quelle: *aggregate/path.md*") plus a deterministic
        # "## Involved aggregates" link list that `matter_files.write_matter_file`
        # always writes, embedding every source path verbatim. Check for that
        # presence instead of a marker format this document type never produces.
        missing = [source for source in sources if source not in document.body]
        findings.append(
            ValidationFinding(
                text="every listed source aggregate path appears in the body",
                passed=not missing,
                evidence=(
                    f"missing references for: {', '.join(missing)}"
                    if missing
                    else f"all {len(sources)} source path(s) referenced"
                ),
            )
        )
    else:
        # `_Source:` lines cite the bare filename (`ingest.py` writes `file_path.name`),
        # while `sources:` in frontmatter is the path relative to the document *root* —
        # comparing the raw strings would false-positive on every aggregate not sitting
        # at the root itself.
        cited = {match.group("name") for match in _SOURCE_MARKER_PATTERN.finditer(document.body)}
        missing = [source for source in sources if Path(source).name not in cited]
        findings.append(
            ValidationFinding(
                text="every listed source has a matching _Source: line in the body",
                passed=not missing,
                evidence=(
                    f"missing citations for: {', '.join(missing)}"
                    if missing
                    else f"{len(cited)} citation(s) found for {len(sources)} source(s)"
                ),
            )
        )

    if sources:
        density = len(body) / len(sources)
        findings.append(
            ValidationFinding(
                text=f"body has at least ~{MIN_BODY_CHARS_PER_SOURCE} characters per source",
                passed=density >= MIN_BODY_CHARS_PER_SOURCE,
                evidence=f"{len(body)} body chars / {len(sources)} source(s) = {density:.0f} chars/source",
            )
        )

    leaked = _LEAKED_FRONTMATTER_PATTERN.findall(body)
    findings.append(
        ValidationFinding(
            text="no nested OKF frontmatter block leaked into the body",
            passed=not leaked,
            evidence=(f"found {len(leaked)} bare 'type: ...' line(s) — a sub-extraction was pasted, not merged"),
        )
    )

    placeholders = _TEMPLATE_PLACEHOLDER_PATTERN.findall(body)
    findings.append(
        ValidationFinding(
            text="no literal prompt-template placeholders (e.g. 'source: path/to/...') in the body",
            passed=not placeholders,
            evidence=f"found placeholder line(s) for: {', '.join(sorted({p[0] for p in placeholders}))}",
        )
    )

    repeated = _find_repeated_blocks(body)
    findings.append(
        ValidationFinding(
            text=f"no paragraph repeated more than {MAX_REPEATED_BLOCK_OCCURRENCES} times (degenerate loop)",
            passed=not repeated,
            evidence=(
                f"{repeated[0][1]}x: {repeated[0][0][:80]}..."
                if repeated
                else "no block exceeded the repetition threshold"
            ),
        )
    )

    body_lower = body.lower()
    found_phrases = [phrase for phrase in _META_COMMENTARY_PHRASES if phrase in body_lower]
    findings.append(
        ValidationFinding(
            text="no chat-reply meta-commentary (e.g. 'here is the output') in the body",
            passed=not found_phrases,
            evidence=f"found: {', '.join(found_phrases)}" if found_phrases else "clean",
        )
    )

    return ValidationReport(path=path, findings=findings)


def validate_tree(root: Path) -> list[ValidationReport]:
    """Validate every FolderSummary/Matter document under root; hidden dirs excluded.

    Returns one report per document found — check `.passed` / `.failures` on each
    rather than filtering here, so callers can report totals (e.g. "12/45 clean").
    """
    reports: list[ValidationReport] = []
    for path in sorted(root.rglob("*.md")):
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        document = load_existing_summary(path)
        if document is not None and document.frontmatter.type in VALIDATABLE_OKF_TYPES:
            reports.append(validate_aggregate(document, path))
    return reports
