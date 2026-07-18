"""Tests for LLMClient's JSONL call logging."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.exceptions import LLMClientError
from app.services.llm_client import LLMClient


def _client(tmp_path: Path, log: bool = True) -> LLMClient:
    return LLMClient(host="http://127.0.0.1:1", log_path=(tmp_path / "log.jsonl") if log else None)


def _fake_success(content: str = "ok") -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def test_successful_call_writes_one_jsonl_record_with_expected_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path)
    monkeypatch.setattr(client._client.chat.completions, "create", lambda **kwargs: _fake_success())

    result = client.chat("system", "a prompt")

    assert result == "ok"
    lines = client.log_path.read_text(encoding="utf-8").strip().splitlines()  # type: ignore[union-attr]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["model"] == client.model
    assert record["host"] == client.host
    assert record["prompt_chars"] == len("a prompt")
    assert record["attempts"] == 1
    assert record["success"] is True
    assert record["error"] is None
    assert isinstance(record["duration_ms"], int)


def test_call_exhausting_retries_logs_failure_and_still_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)

    def _always_fail(**kwargs: object) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(client._client.chat.completions, "create", _always_fail)
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda _seconds: None)

    with pytest.raises(LLMClientError):
        client.chat("system", "a prompt")

    lines = client.log_path.read_text(encoding="utf-8").strip().splitlines()  # type: ignore[union-attr]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["attempts"] == 3
    assert record["success"] is False
    assert "connection refused" in record["error"]


def test_no_log_path_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path, log=False)
    monkeypatch.setattr(client._client.chat.completions, "create", lambda **kwargs: _fake_success())

    client.chat("system", "a prompt")

    assert not (tmp_path / "log.jsonl").exists()
