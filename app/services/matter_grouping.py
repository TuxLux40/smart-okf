"""Cheap, non-LLM pre-filter for candidate cross-folder matters.

Groups aggregates that share a probable reference number (contract, customer, case,
meter, or account ID — anything 5+ consecutive digits, or alphanumerics like
`13040393S105`) before any deep-dive LLM call touches them. This keeps the expensive
pass (`app/services/dream.py`'s per-matter deep dive, which reads full aggregate bodies)
bounded to genuinely related aggregates instead of scaling with tree size: number of
deep-dive calls = number of candidate groups, not number of aggregates.
"""

import re
from pathlib import Path

DEFAULT_MIN_TOKEN_DIGITS = 5
"""Baseline minimum length for a numeric token to count as a shared identifier — the
`provenance` ordering principle. `pertinence` lowers it (more, looser cross-folder
groups); a stricter setting raises it. See `app/config.py::ordering_principle`."""

_YEAR_TOKEN = re.compile(r"^(?:19|20)\d{2}$")
"""Bare calendar years must never alone merge unrelated folders into one matter."""

_ALPHANUM_CANDIDATE = re.compile(r"[A-Za-z0-9]{6,}")
"""Candidates for mixed alphanumerics; refined by digit/letter counts below."""


def min_token_digits_for_principle(ordering_principle: str) -> int:
    """Map an archival ordering principle to the shared-identifier minimum length.

    `provenance` (respect folders, conservative) keeps the default; `pertinence` (lean into
    cross-folder subject synthesis) lowers the bar so weaker numeric matches also form
    matters — the one concrete, measurable effect of the principle choice.
    """
    return 4 if ordering_principle == "pertinence" else DEFAULT_MIN_TOKEN_DIGITS


def _is_alphanum_reference(token: str) -> bool:
    """True for mixed refs like `13040393S105` / `371D079997` (≥2 digits, ≥1 letter, len≥6)."""
    if len(token) < 6:
        return False
    digits = sum(character.isdigit() for character in token)
    letters = sum(character.isalpha() for character in token)
    return digits >= 2 and letters >= 1


def extract_numeric_tokens(text: str, *, min_digits: int = DEFAULT_MIN_TOKEN_DIGITS) -> set[str]:
    """Return likely contract/customer/meter/case IDs from free text (or a digest).

    Includes:
    - pure digit runs of at least `min_digits` (default 5), excluding bare years `19xx`/`20xx`
      so a shared calendar year never merges two unrelated folders;
    - alphanumerics of length ≥6 with ≥2 digits and ≥1 letter (`13040393S105`,
      `1ISK0069105958`, `371D079997`).

    Prefer feeding digests that already carry an `Identifiers:` line (from
    `build_digest`) so values come from the structured frontmatter map; free-text
    extraction still applies the same filters for older aggregates without that line.
    """
    tokens: set[str] = set()
    for match in re.findall(rf"\d{{{min_digits},}}", text):
        if _YEAR_TOKEN.fullmatch(match):
            continue
        tokens.add(match)
    for candidate in _ALPHANUM_CANDIDATE.findall(text):
        if _is_alphanum_reference(candidate):
            tokens.add(candidate)
    return tokens


def group_by_shared_tokens(digests: dict[Path, str], *, min_digits: int = DEFAULT_MIN_TOKEN_DIGITS) -> list[list[Path]]:
    """Group aggregate paths that share at least one numeric token of `min_digits`+ digits.

    Union-find over token -> paths, so a token linking A-B and a different token
    linking B-C merge into one group {A, B, C}. Singletons (no shared token with
    any other aggregate) are excluded from the result — nothing to correlate, and
    the cheap digest-based pass already covers them for Patterns/general context.
    """
    parent: dict[Path, Path] = {path: path for path in digests}

    def find(x: Path) -> Path:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: Path, b: Path) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    token_to_paths: dict[str, list[Path]] = {}
    for path, text in digests.items():
        for token in extract_numeric_tokens(text, min_digits=min_digits):
            token_to_paths.setdefault(token, []).append(path)

    for paths in token_to_paths.values():
        for other in paths[1:]:
            union(paths[0], other)

    groups: dict[Path, list[Path]] = {}
    for path in digests:
        groups.setdefault(find(path), []).append(path)

    return [sorted(members, key=str) for members in groups.values() if len(members) > 1]


def group_tokens(group: list[Path], digests: dict[Path, str]) -> list[str]:
    """Return the numeric tokens shared by 2+ members of this specific group, sorted.

    A group can form via a token chain (A-B share token1, B-C share token2) without A and
    C sharing anything directly. Both tokens still identify the group for naming purposes,
    so this recounts token occurrences confined to `group`'s own members rather than reusing
    `group_by_shared_tokens`'s global union-find state. Used to build a stable, human-legible
    slug for the matter's persisted file (`app/services/matter_files.py`) — stable across
    dream reruns as long as the same aggregates keep sharing the same token.
    """
    counts: dict[str, int] = {}
    for path in group:
        for token in extract_numeric_tokens(digests.get(path, "")):
            counts[token] = counts.get(token, 0) + 1
    return sorted(token for token, count in counts.items() if count > 1)
