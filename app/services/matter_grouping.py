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

_NUMERIC_TOKEN = re.compile(r"\d{5,}")


def extract_numeric_tokens(text: str) -> set[str]:
    """Return 5+ digit numeric substrings — likely contract/customer/meter/case IDs.

    5 digits is deliberately low: German utility/insurance/case references are
    commonly 6-10 digits, but shorter postal/customer codes exist too. False
    positives (e.g. a stray year-like number) just mean a slightly bigger deep-dive
    group — the deep-dive prompt is instructed to say "not the same matter" when the
    shared number turns out to be coincidental, rather than forcing a connection.
    """
    return set(_NUMERIC_TOKEN.findall(text))


def group_by_shared_tokens(digests: dict[Path, str]) -> list[list[Path]]:
    """Group aggregate paths that share at least one 5+ digit numeric token.

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
        for token in extract_numeric_tokens(text):
            token_to_paths.setdefault(token, []).append(path)

    for paths in token_to_paths.values():
        for other in paths[1:]:
            union(paths[0], other)

    groups: dict[Path, list[Path]] = {}
    for path in digests:
        groups.setdefault(find(path), []).append(path)

    return [sorted(members, key=str) for members in groups.values() if len(members) > 1]
