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

from app.constants import FOLDER_SUMMARY_OKF_TYPE, MATTER_OKF_TYPE, TRANSCRIPTS_DIR_NAME
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

# --- Identifier-loss check (transcript vs aggregate body) ---
# Precision over recall: only label-driven matches and a few high-confidence free-form
# patterns. Bare 4–6 digit runs without a label are intentionally ignored (page numbers,
# PLZ, date fragments, OCR noise).

_IDENTIFIER_LABELS = (
    "Rentenversicherungsnummer",
    "Versicherungsnummer",
    "Versichertennummer",
    "Mitgliedsnummer",
    "Personalnummer",
    "Kundennummer",
    "Vertragsnummer",
    "Rechnungsnummer",
    "Bestellnummer",
    "Auftragsnummer",
    "Antragsnummer",
    "Aktenzeichen",
    "Geschäftszeichen",
    "Betriebsnummer",
    "Betr-Nr",
    "Tätigkeitsschlüssel",
    "Dienststelle",
    "Kostenstelle",
    "Steuer-ID",
    "IdNr",
    "Steuernummer",
    "Zählernummer",
    "Zählpunkt",
    "Marktlokation",
    "Gläubiger-ID",
    "Mandatsreferenz",
    "Depotnummer",
    "Depot",
    "IBAN",
    "BIC",
    "ISIN",
)
"""German document labels that precede a durable identifier. Longer labels first so
`Rentenversicherungsnummer` wins over bare `Versicherungsnummer` when both match."""

_VALUE_FIRST_TOKEN = r"[A-Za-z0-9](?:[A-Za-z0-9./-]*[A-Za-z0-9])?"
"""The identifier's first token: alnum, optionally with internal `.`/`/`/`-`
(covers `12`, `1383617673`, `13040393S105`)."""

_VALUE_CONT_TOKEN = r"(?:\b[A-Za-z]\b|[A-Za-z0-9./-]*\d[A-Za-z0-9./-]*)"
"""A token that can *continue* a split identifier value: either a single stray letter
(`S`, `O` — the middle letter of an RVNR or an Aktenzeichen court code) or any token that
itself contains a digit (`105`, `345/23`). Deliberately excludes multi-letter, digit-free
words — `des`, `vor`, `Bank`, `GmbH` — so trailing prose after the real value is never
swallowed. `\\b[A-Za-z]\\b` (not bare `[A-Za-z]`) so it can't match just the first letter
of a longer word."""

_LABEL_PATTERN = re.compile(
    r"(?P<label>"
    + "|".join(re.escape(label) for label in sorted(_IDENTIFIER_LABELS, key=len, reverse=True))
    + r")[\s:]*(?P<value>"
    + _VALUE_FIRST_TOKEN
    + r"(?: "
    + _VALUE_CONT_TOKEN
    + r"){0,3})",
    re.IGNORECASE | re.MULTILINE,
)
"""Captures up to 4 space-separated value tokens after a label — enough for split forms
like `13040393 S 105` or `12 O 345/23` — without swallowing trailing prose. A naive
`\\S[^\\n]*` here would capture 'Kundennummer: 1383617673 (SWK Bank Finanzierung GmbH)'
as one value, which then never matches the aggregate body verbatim (false FLAGGED)."""

_IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_STEUER_ID_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")
_RVNR_PATTERN = re.compile(r"\b\d{8}[A-Z]\d{3}\b", re.IGNORECASE)
_ISIN_PATTERN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b", re.IGNORECASE)

_MAX_MISSING_EVIDENCE = 8
"""Cap listed missing identifiers in a finding so a catastrophic loss stays readable."""


def _normalize_identifier(value: str) -> str:
    """Strip spaces and dots so `13040393 S 105` matches `13040393S105`."""
    return re.sub(r"[\s.]", "", value)


def extract_identifiers_from_transcript(text: str) -> list[tuple[str, str]]:
    """Return (label, value) pairs found in raw transcript text.

    Label-driven matches use the curated German list; free-form patterns only cover
    formats confident enough to stand alone (IBAN, Steuer-ID, RVNR, ISIN).
    """
    found: list[tuple[str, str]] = []
    seen_normalized: set[str] = set()

    def _add(label: str, value: str) -> None:
        cleaned = value.strip().rstrip(".,;:")
        if not cleaned:
            return
        key = _normalize_identifier(cleaned).upper()
        if not key or key in seen_normalized:
            return
        seen_normalized.add(key)
        found.append((label, cleaned))

    for match in _LABEL_PATTERN.finditer(text):
        _add(match.group("label"), match.group("value"))

    for match in _IBAN_PATTERN.finditer(text):
        _add("IBAN", match.group(0))
    for match in _STEUER_ID_PATTERN.finditer(text):
        _add("Steuer-ID", match.group(0))
    for match in _RVNR_PATTERN.finditer(text):
        _add("Rentenversicherungsnummer", match.group(0))
    for match in _ISIN_PATTERN.finditer(text):
        _add("ISIN", match.group(0))

    return found


def _identifier_present_in_body(value: str, body_normalized: str) -> bool:
    """True if the identifier's normalized form appears in the normalized body."""
    needle = _normalize_identifier(value).upper()
    return bool(needle) and needle in body_normalized


def _transcript_path_for_source(transcripts_root: Path, source: str) -> Path:
    """Resolve `.okf-transcripts/<relpath>.txt` for a frontmatter source path."""
    relative = Path(source)
    return transcripts_root / relative.parent / f"{relative.name}.txt"


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


def _check_identifiers_from_transcripts(
    document: OKFDocument,
    *,
    transcripts_root: Path | None,
) -> ValidationFinding:
    """Deterministic check: labeled/format identifiers in transcripts must appear in body.

    No transcript available (missing root, missing files, empty sources) → skip with a
    note, not a failure — tree coverage is still patchy until a full re-ingest.
    """
    finding_text = "identifiers from the source transcript appear in the aggregate"
    if transcripts_root is None or not document.frontmatter.sources:
        return ValidationFinding(
            text=finding_text,
            passed=True,
            evidence="no transcript available — identifier check skipped",
        )

    collected: list[tuple[str, str]] = []
    any_transcript = False
    for source in document.frontmatter.sources:
        path = _transcript_path_for_source(transcripts_root, source)
        if not path.is_file():
            continue
        any_transcript = True
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        collected.extend(extract_identifiers_from_transcript(text))

    if not any_transcript:
        return ValidationFinding(
            text=finding_text,
            passed=True,
            evidence="no transcript available — identifier check skipped",
        )

    if not collected:
        return ValidationFinding(
            text=finding_text,
            passed=True,
            evidence="no labeled/high-confidence identifiers found in transcript(s)",
        )

    body_normalized = _normalize_identifier(document.body).upper()
    missing = [(label, value) for label, value in collected if not _identifier_present_in_body(value, body_normalized)]
    if not missing:
        return ValidationFinding(
            text=finding_text,
            passed=True,
            evidence=f"all {len(collected)} transcript identifier(s) present in body",
        )

    shown = missing[:_MAX_MISSING_EVIDENCE]
    listed = ", ".join(f"{label}={value}" for label, value in shown)
    extra = f" (+{len(missing) - len(shown)} more)" if len(missing) > len(shown) else ""
    return ValidationFinding(
        text=finding_text,
        passed=False,
        evidence=f"missing: {listed}{extra}",
    )


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


def validate_aggregate(
    document: OKFDocument,
    path: Path,
    *,
    transcripts_root: Path | None = None,
) -> ValidationReport:
    """Run heuristic plausibility checks against one FolderSummary/Matter document.

    `transcripts_root` is the `.okf-transcripts/` directory (sibling-tree of source
    transcripts). When omitted or when a source has no transcript yet, the identifier-loss
    check is skipped (passed with a note) rather than failed — coverage is still patchy
    until a full re-ingest rewrites transcripts for every source.
    """
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

    findings.append(_check_identifiers_from_transcripts(document, transcripts_root=transcripts_root))

    return ValidationReport(path=path, findings=findings)


def render_validation_banner(report: ValidationReport) -> str:
    """One `_Verification: FLAGGED — <reason>_` line per failed check in `report`.

    Reuses `render_section`'s existing per-document marker convention (a failed fact-check
    on one source document already renders as `_Verification: FLAGGED — <reason>_` inline)
    so a folder-level heuristic failure — fabricated placeholder, missing citations, a body
    too thin for its source count — is visible the same way, in the same file, without a
    reader needing to separately run `validate_okf.py` and cross-reference paths by hand.
    `ingest.py`/`matter_files.py` prepend this to the body whenever `validate_aggregate`
    fails, so "no `_Verification: FLAGGED` anywhere in this file" becomes a reliable signal
    that the aggregate/matter can be trusted without reopening the source documents.
    """
    return "\n\n".join(f"_Verification: FLAGGED — {finding.text}: {finding.evidence}_" for finding in report.failures)


def validate_tree(root: Path) -> list[ValidationReport]:
    """Validate every FolderSummary/Matter document under root; hidden dirs excluded.

    Returns one report per document found — check `.passed` / `.failures` on each
    rather than filtering here, so callers can report totals (e.g. "12/45 clean").
    Transcripts are resolved under `<root>/.okf-transcripts/` when present.
    """
    transcripts_root = root / TRANSCRIPTS_DIR_NAME
    reports: list[ValidationReport] = []
    for path in sorted(root.rglob("*.md")):
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        document = load_existing_summary(path)
        if document is not None and document.frontmatter.type in VALIDATABLE_OKF_TYPES:
            reports.append(validate_aggregate(document, path, transcripts_root=transcripts_root))
    return reports
