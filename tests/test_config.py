"""Tests for SmartOkfConfig loading and llm_host allowlist validation."""

import pytest
from pydantic import ValidationError

from app.config import SmartOkfConfig, host_is_allowlisted, parse_llm_host


def _config(**overrides: object) -> SmartOkfConfig:
    defaults: dict[str, object] = {"document_roots": ["/tmp/docs"]}
    defaults.update(overrides)
    return SmartOkfConfig(**defaults)  # type: ignore[arg-type]


def test_document_roots_requires_at_least_one_path() -> None:
    with pytest.raises(ValidationError):
        _config(document_roots=[])


def test_document_roots_normalized_to_resolved_paths() -> None:
    config = _config(document_roots=["~/docs"])
    assert config.document_roots[0].is_absolute()


@pytest.mark.parametrize(
    "llm_host",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://192.168.1.10:11434",
        "localhost:11434",
    ],
)
def test_llm_host_allowlisted_values_pass(llm_host: str) -> None:
    config = _config(llm_host=llm_host)
    assert config.llm_host == llm_host


def test_llm_host_remote_rejected_without_allow_remote_llm() -> None:
    with pytest.raises(ValidationError):
        _config(llm_host="https://api.openai.com/v1")


def test_llm_host_remote_allowed_with_allow_remote_llm() -> None:
    config = _config(llm_host="https://api.openai.com/v1", allow_remote_llm=True)
    assert config.llm_host == "https://api.openai.com/v1"


def test_parse_llm_host_extracts_hostname_from_url() -> None:
    assert parse_llm_host("http://localhost:11434") == "localhost"


def test_parse_llm_host_extracts_hostname_from_bare_host_port() -> None:
    assert parse_llm_host("localhost:11434") == "localhost"


def test_host_is_allowlisted_rejects_unknown_public_host() -> None:
    assert host_is_allowlisted("api.openai.com", []) is False


def test_host_is_allowlisted_accepts_rfc1918() -> None:
    assert host_is_allowlisted("10.0.0.5", []) is True
