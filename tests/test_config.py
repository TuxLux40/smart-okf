"""Tests for SmartOkfConfig loading and llm_host allowlist validation."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.config import (
    SmartOkfConfig,
    config_path_for_root,
    host_is_allowlisted,
    load_config,
    parse_llm_host,
    resolve_document_root,
)


def _config(**overrides: object) -> SmartOkfConfig:
    return SmartOkfConfig(**overrides)  # type: ignore[arg-type]


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


def test_dream_model_and_host_default_to_none_fallback_to_extractor() -> None:
    config = _config()
    assert config.dream_model is None
    assert config.dream_host is None


def test_dream_host_remote_refused_without_allow_remote_llm() -> None:
    with pytest.raises(ValidationError, match="dream_host"):
        _config(dream_host="https://api.openai.com/v1")


def test_dream_host_remote_allowed_with_allow_remote_llm() -> None:
    config = _config(dream_host="https://api.openai.com/v1", allow_remote_llm=True)
    assert config.dream_host == "https://api.openai.com/v1"


def test_dream_host_local_allowed_by_default() -> None:
    config = _config(dream_host="http://192.168.178.2:8080")
    assert config.dream_host == "http://192.168.178.2:8080"


def test_ordering_principle_defaults_to_provenance() -> None:
    assert _config().ordering_principle == "provenance"


def test_ordering_principle_accepts_pertinence() -> None:
    assert _config(ordering_principle="pertinence").ordering_principle == "pertinence"


def test_ordering_principle_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="ordering_principle"):
        _config(ordering_principle="thematic")


def test_gating_and_derive_defaults() -> None:
    config = _config()
    assert config.exclude_patterns == []
    assert config.low_priority_patterns == []
    assert config.priority_patterns == []
    assert config.derive_per_file is False
    assert config.generate_readme is True


def test_content_language_defaults_to_none() -> None:
    assert _config().content_language is None


def test_content_language_accepts_a_language_code() -> None:
    assert _config(content_language="de").content_language == "de"


def test_config_path_for_root_is_hidden_folder_inside_root(tmp_path: Path) -> None:
    assert config_path_for_root(tmp_path) == tmp_path / ".smart-okf" / "config.yaml"


def test_load_config_returns_none_without_a_config_file(tmp_path: Path) -> None:
    assert load_config(tmp_path) is None


def test_resolve_document_root_returns_start_when_no_config_anywhere(tmp_path: Path) -> None:
    assert resolve_document_root(tmp_path) == tmp_path


def test_resolve_document_root_returns_start_when_config_is_at_start(tmp_path: Path) -> None:
    (tmp_path / ".smart-okf").mkdir()
    (tmp_path / ".smart-okf" / "config.yaml").write_text("llm_model: foo\n", encoding="utf-8")

    assert resolve_document_root(tmp_path) == tmp_path


def test_resolve_document_root_walks_up_to_the_ancestor_with_config(tmp_path: Path) -> None:
    (tmp_path / ".smart-okf").mkdir()
    (tmp_path / ".smart-okf" / "config.yaml").write_text("llm_model: foo\n", encoding="utf-8")
    subfolder = tmp_path / "finances" / "banks"
    subfolder.mkdir(parents=True)

    assert resolve_document_root(subfolder) == tmp_path


def test_load_config_reads_yaml_from_the_document_root(tmp_path: Path) -> None:
    config_dir = tmp_path / ".smart-okf"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(yaml.dump({"llm_model": "qwen2.5:7b", "ordering_principle": "pertinence"}))

    config = load_config(tmp_path)

    assert config is not None
    assert config.llm_model == "qwen2.5:7b"
    assert config.ordering_principle == "pertinence"


def test_load_config_env_var_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / ".smart-okf"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(yaml.dump({"llm_model": "qwen2.5:7b"}))
    monkeypatch.setenv("SMART_OKF_LLM_MODEL", "gemma-4b")

    config = load_config(tmp_path)

    assert config is not None
    assert config.llm_model == "gemma-4b"


def test_load_config_does_not_leak_across_different_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    (root_a / ".smart-okf").mkdir(parents=True)
    (root_a / ".smart-okf" / "config.yaml").write_text(yaml.dump({"llm_model": "model-a"}))

    assert load_config(root_a) is not None
    assert load_config(root_a).llm_model == "model-a"  # type: ignore[union-attr]
    assert load_config(root_b) is None


def test_load_config_walks_up_to_an_ancestor_root(tmp_path: Path) -> None:
    """A subfolder of an already-onboarded root (e.g. an ingest smoke test on one
    subfolder, per SKILL.md) must still resolve the root's config, not silently fall back
    to built-in defaults."""
    root = tmp_path / "documents"
    subfolder = root / "apartments" / "Quantiusstrasse"
    subfolder.mkdir(parents=True)
    (root / ".smart-okf").mkdir()
    (root / ".smart-okf" / "config.yaml").write_text(yaml.dump({"llm_model": "model-root"}))

    config = load_config(subfolder)

    assert config is not None
    assert config.llm_model == "model-root"
