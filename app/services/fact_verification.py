"""Per-document fact verification: does an extraction actually reflect its source?

Mandatory step of ingest, not opt-in — this project's core purpose is atomic facts
an agent can trust; an unverified extraction defeats that purpose regardless of the
compute it would save to skip it. Kept as cheap as a "must always run" check can be:
one call per already-extracted document, reusing the source text already read for
extraction (no re-OCR, no re-read) against that document's own output — not a
second full re-extraction, and not a whole-tree re-analysis pass.

The heuristic checks in `app/services/validation.py` catch specific *shapes* a bad
extraction takes (empty, templated, repeated, leaked-prompt) without needing a model
call at all. This module catches what those structurally can't: a fluent, well-formed
extraction that simply states something the source document never said. Both matter;
neither replaces the other.
"""

from dataclasses import dataclass

from app.constants import VERIFICATION_FLAGGED_MARKER
from app.services.llm_client import LLMClient


@dataclass
class FactVerificationResult:
    """Verdict for one document's extraction against its source text."""

    passed: bool
    issue: str = ""


def verify_extraction(source_text: str, extracted_markdown: str, client: LLMClient) -> FactVerificationResult:
    """Ask `client` whether `extracted_markdown` is traceable to `source_text`.

    Tolerant of a verifier that doesn't follow the "OK" / "FLAGGED: ..." format exactly
    (small local models drift) — anything not starting with the flagged marker counts as
    passed, matching this project's preference for surfacing stale-but-present data over
    silently dropping it (see `ingest.py`'s failed-re-extraction handling for the same
    principle applied to extraction itself).
    """
    response = client.verify_facts(source_text, extracted_markdown).strip()
    if response.upper().startswith(VERIFICATION_FLAGGED_MARKER):
        issue = response[len(VERIFICATION_FLAGGED_MARKER) :].lstrip(": -—").strip()
        return FactVerificationResult(passed=False, issue=issue or "flagged with no reason given")
    return FactVerificationResult(passed=True)
