"""Cheap, non-LLM pre-filter for candidate cross-folder matters.

Groups aggregates that share a probable reference number (contract, customer, case,
meter, or account ID — anything 5+ consecutive digits) before any deep-dive LLM call
touches them. This keeps the expensive pass (`app/services/dream.py`'s per-matter
deep dive, which reads full aggregate bodies) bounded to genuinely related aggregates
instead of scaling with tree size: number of deep-dive calls = number of candidate
groups, not number of aggregates.
"""

import re
from pathlib import Path

DEFAULT_MIN_TOKEN_DIGITS = 5
"""Baseline minimum length for a numeric token to count as a shared identifier — the
`provenance` ordering principle. `pertinence` lowers it (more, looser cross-folder
groups); a stricter setting raises it. See `app/config.py::ordering_principle`."""


def min_token_digits_for_principle(ordering_principle: str) -> int:
    """Map an archival ordering principle to the shared-identifier minimum length.

    `provenance` (respect folders, conservative) keeps the default; `pertinence` (lean into
    cross-folder subject synthesis) lowers the bar so weaker numeric matches also form
    matters — the one concrete, measurable effect of the principle choice.
    """
    return 4 if ordering_principle == "pertinence" else DEFAULT_MIN_TOKEN_DIGITS


def extract_numeric_tokens(text: str, *, min_digits: int = DEFAULT_MIN_TOKEN_DIGITS) -> set[str]:
    """Return numeric substrings of at least `min_digits` digits — likely contract/customer/
    meter/case IDs.

    The default 5 is deliberately low: German utility/insurance/case references are
    commonly 6-10 digits, but shorter postal/customer codes exist too. False
    positives (e.g. a stray year-like number) just mean a slightly bigger deep-dive
    group — the deep-dive prompt is instructed to say "not the same matter" when the
    shared number turns out to be coincidental, rather than forcing a connection.
    """
    return set(re.findall(rf"\d{{{min_digits},}}", text))


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
