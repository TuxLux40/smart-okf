"""Ingest gating: keep junk out of extraction, keep low-value docs out of deep analysis.

Two independent decisions, deterministic and free (no LLM call — pattern/keyword only):

- **exclude** (`is_excluded`): the file is not ingested at all. For documents that carry
  no durable personal facts worth extracting — manuals, terms of service, marketing.
- **deprioritize** (`is_deprioritized`): the file/folder is ingested normally (transcript +
  derive + aggregate) but kept out of the expensive cross-folder `dream` pass. The default
  stance is *eager*: anything matching a built-in trivial-name keyword or a user
  low-priority pattern is deprioritized unless the user explicitly marked it priority — so
  budget goes to documents that actually describe the user's affairs, not boilerplate that
  happened to land in the tree.

An optional LLM-classifier fallback (`classify_relevance_llm`) exists for the ambiguous
case a filename can't settle, but it is opt-in: deterministic rules run first and decide
the vast majority for free; the model is only consulted when explicitly enabled.
"""

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath

DEFAULT_TRIVIAL_KEYWORDS: frozenset[str] = frozenset(
    {
        # German
        "agb",
        "bedienungsanleitung",
        "gebrauchsanweisung",
        "handbuch",
        "widerruf",
        "widerrufsbelehrung",
        "datenschutzerklaerung",
        "datenschutzerklärung",
        "nutzungsbedingungen",
        "werbung",
        "prospekt",
        "katalog",
        # English
        "manual",
        "userguide",
        "user-guide",
        "terms",
        "termsofservice",
        "tos",
        "privacy",
        "privacypolicy",
        "withdrawal",
        "cancellationpolicy",
        "advertisement",
        "advertising",
        "catalog",
        "catalogue",
        "brochure",
        "newsletter",
        "flyer",
        # French
        "manueldutilisation",
        "modedemploi",
        "conditionsgenerales",
        "conditionsgénérales",
        "cgu",
        "cgv",
        "politiquedeconfidentialite",
        "politiquedeconfidentialité",
        "retractation",
        "rétractation",
        "publicite",
        "publicité",
        "prospectus",
        "infolettre",
        # Spanish
        "manualdeusuario",
        "terminosycondiciones",
        "términosycondiciones",
        "condicionesdeuso",
        "politicadeprivacidad",
        "políticadeprivacidad",
        "derechodedesistimiento",
        "publicidad",
        "catalogo",
        "catálogo",
        "folleto",
        "boletin",
        "boletín",
        # Italian
        "manualedistruzioni",
        "terminicondizioni",
        "condizionidiutilizzo",
        "informativaprivacy",
        "dirittodirecesso",
        "recesso",
        "pubblicita",
        "pubblicità",
        "opuscolo",
        "volantino",
        # Dutch
        "handleiding",
        "gebruiksaanwijzing",
        "algemenevoorwaarden",
        "privacybeleid",
        "herroepingsrecht",
        "reclame",
        "catalogus",
        "nieuwsbrief",
    }
)
"""Filename/path substrings that mark a document as boilerplate — deprioritized eagerly
(kept out of `dream`) even when the user listed no patterns. Covers German, English,
French, Spanish, Italian, and Dutch, since documents may arrive in any of those. Deliberately
conservative: these words rarely appear in documents carrying personal facts (contracts,
letters, statements), so a match is a strong low-value signal — generic short words that
could collide with real folder/file names (e.g. a bare "folder") are intentionally left out.
Never used to *exclude* from ingest (too risky to silently drop a file on a keyword) — only
to deprioritize."""


@dataclass
class GatingRules:
    """Resolved gating configuration for one ingest/dream run."""

    exclude_patterns: list[str] = field(default_factory=list)
    """Glob patterns (matched against the root-relative POSIX path and the bare filename).
    A match means the file is never ingested."""

    low_priority_patterns: list[str] = field(default_factory=list)
    """Glob patterns that deprioritize a file/folder (ingested, but excluded from dream)."""

    priority_patterns: list[str] = field(default_factory=list)
    """Glob patterns that force priority — always deep-analyzed, overriding both the
    low-priority patterns and the built-in trivial-name heuristic."""

    trivial_keywords: frozenset[str] = DEFAULT_TRIVIAL_KEYWORDS
    """Built-in low-value keyword set for eager deprioritization; override to disable/extend."""


def _matches_any(relative_path: str, patterns: list[str]) -> bool:
    """True if the root-relative POSIX path or its bare filename matches any glob pattern."""
    name = PurePosixPath(relative_path).name
    return any(fnmatch(relative_path, pattern) or fnmatch(name, pattern) for pattern in patterns)


def is_excluded(relative_path: str, rules: GatingRules) -> bool:
    """Whether a file must not be ingested at all (matches an exclude pattern)."""
    return _matches_any(relative_path, rules.exclude_patterns)


def is_deprioritized(relative_path: str, rules: GatingRules) -> bool:
    """Whether a file/folder is ingested but kept out of the deep `dream` pass.

    Priority patterns win over everything. Otherwise a low-priority pattern OR a built-in
    trivial-name keyword (eager default) deprioritizes it. A path with no signal at all is
    NOT deprioritized — normal documents still reach dream.
    """
    if _matches_any(relative_path, rules.priority_patterns):
        return False
    if _matches_any(relative_path, rules.low_priority_patterns):
        return True
    lowered = relative_path.lower()
    return any(keyword in lowered for keyword in rules.trivial_keywords)
