"""Unit tests for `app/services/fact_verification.py`."""

from app.services.fact_verification import verify_extraction


class _StubClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def verify_facts(self, source_text: str, extracted_markdown: str, *, max_tokens: int | None = None) -> str:
        return self._response


def test_ok_response_passes() -> None:
    result = verify_extraction("source", "extracted", _StubClient("OK"))  # type: ignore[arg-type]
    assert result.passed
    assert result.issue == ""


def test_flagged_response_fails_with_parsed_reason() -> None:
    client = _StubClient("FLAGGED: fabricated total not in source")
    result = verify_extraction("source", "extracted", client)  # type: ignore[arg-type]
    assert not result.passed
    assert result.issue == "fabricated total not in source"


def test_flagged_response_without_separator_still_parses() -> None:
    client = _StubClient("FLAGGED fabricated content")
    result = verify_extraction("source", "extracted", client)  # type: ignore[arg-type]
    assert not result.passed
    assert result.issue == "fabricated content"


def test_flagged_with_no_reason_gets_placeholder() -> None:
    result = verify_extraction("source", "extracted", _StubClient("FLAGGED:"))  # type: ignore[arg-type]
    assert not result.passed
    assert result.issue == "flagged with no reason given"


def test_flagged_marker_is_case_insensitive() -> None:
    client = _StubClient("flagged: lowercase reason")
    result = verify_extraction("source", "extracted", client)  # type: ignore[arg-type]
    assert not result.passed
    assert result.issue == "lowercase reason"


def test_nonconforming_response_is_treated_as_passed() -> None:
    client = _StubClient("Sure, this looks fine to me!")
    result = verify_extraction("source", "extracted", client)  # type: ignore[arg-type]
    assert result.passed


def test_response_is_stripped_of_surrounding_whitespace() -> None:
    result = verify_extraction("source", "extracted", _StubClient("  OK  \n"))  # type: ignore[arg-type]
    assert result.passed
