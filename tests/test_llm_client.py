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


def test_describe_image_without_vision_model_raises(tmp_path: Path) -> None:
    client = LLMClient(host="http://127.0.0.1:1", vision_model=None)
    image_path = tmp_path / "meter.jpg"
    image_path.write_bytes(b"\xff\xd8\xff fake jpeg bytes")

    with pytest.raises(LLMClientError, match="vision_model"):
        client.describe_image(image_path)


def test_describe_image_sends_base64_image_to_configured_vision_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = LLMClient(host="http://127.0.0.1:1", vision_model="qwen3-vl-8b-instruct")
    image_path = tmp_path / "meter.jpg"
    image_path.write_bytes(b"\xff\xd8\xff fake jpeg bytes")

    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return _fake_success("123456 kWh, meter photo")

    monkeypatch.setattr(client._client.chat.completions, "create", _capture)

    result = client.describe_image(image_path, context="providers/EON/meter.jpg")

    assert result == "123456 kWh, meter photo"
    assert captured["model"] == "qwen3-vl-8b-instruct"
    messages = captured["messages"]
    assert isinstance(messages, list)
    user_content = messages[1]["content"]
    assert user_content[0]["text"] == "Image: providers/EON/meter.jpg"
    assert user_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_describe_image_logs_vision_model_not_extraction_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSONL must record the model used for the call (vision), not only self.model."""
    log_path = tmp_path / "log.jsonl"
    client = LLMClient(
        host="http://127.0.0.1:1",
        model="extraction-model",
        vision_model="vision-model",
        log_path=log_path,
    )
    image_path = tmp_path / "meter.jpg"
    image_path.write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    monkeypatch.setattr(client._client.chat.completions, "create", lambda **kwargs: _fake_success("ok"))

    client.describe_image(image_path)

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["model"] == "vision-model"


def _fake_models_list(*ids: str) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in ids])


def test_available_models_returns_ids_from_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path, log=False)
    monkeypatch.setattr(client._client.models, "list", lambda: _fake_models_list("gemma-4-e4b", "llama-3.2-1b"))

    assert client.available_models() == ["gemma-4-e4b", "llama-3.2-1b"]


def test_available_models_raises_llm_client_error_on_connection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, log=False)

    def _fail() -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(client._client.models, "list", _fail)

    with pytest.raises(LLMClientError):
        client.available_models()


def test_confirm_model_available_passes_silently_when_model_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = LLMClient(host="http://127.0.0.1:1", model="gemma-4-e4b")
    monkeypatch.setattr(client._client.models, "list", lambda: _fake_models_list("gemma-4-e4b"))

    client.confirm_model_available()  # must not raise


def test_confirm_model_available_raises_with_configured_and_actual_models_in_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = LLMClient(host="http://127.0.0.1:1", model="google/gemma-4-e4b")
    monkeypatch.setattr(client._client.models, "list", lambda: _fake_models_list("llama-3.2-1b-instruct"))

    with pytest.raises(LLMClientError) as excinfo:
        client.confirm_model_available()

    message = str(excinfo.value)
    assert "google/gemma-4-e4b" in message
    assert "llama-3.2-1b-instruct" in message
