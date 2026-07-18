"""LLM client for any OpenAI-compatible chat completions backend.

Works unmodified against Ollama, llama.cpp's `llama-server`, vLLM, LM Studio, or hosted
OpenAI-compatible APIs — anything serving `POST {host}/v1/chat/completions`.
"""

import contextlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI

from app.constants import (
    DEFAULT_EXTRACTION_USER_SUFFIX,
    DEFAULT_LLM_HOST,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
)
from app.exceptions import LLMClientError
from app.services.prompts import load_extraction_prompt, load_folder_summary_prompt

_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0


def _as_v1_base_url(host: str) -> str:
    """Normalize a bare host into an OpenAI-compatible `/v1` base URL."""
    host = host.rstrip("/")
    return host if host.endswith("/v1") else f"{host}/v1"


class LLMClient:
    """Chat client for extraction and reasoning tasks against a local or remote LLM."""

    def __init__(
        self,
        model: str = DEFAULT_LLM_MODEL,
        host: str | None = None,
        api_key: str | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        log_path: Path | None = None,
    ) -> None:
        self.model = model
        self.host: str = host if host is not None else os.getenv("SMART_OKF_LLM_HOST", DEFAULT_LLM_HOST)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.log_path = log_path
        self._client = OpenAI(
            base_url=_as_v1_base_url(self.host),
            api_key=api_key or os.getenv("SMART_OKF_LLM_API_KEY", "not-needed"),
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Run a chat completion and return the assistant response text.

        Local servers (LM Studio, llama.cpp) occasionally fail transiently under
        sequential load, so requests are retried with backoff before giving up.
        """
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                )
                content = (response.choices[0].message.content or "").strip()
                self._log_call(user_prompt, attempt + 1, time.monotonic() - started, success=True)
                return content
            except Exception as error:
                last_error = error
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        self._log_call(user_prompt, _MAX_ATTEMPTS, time.monotonic() - started, success=False, error=str(last_error))
        raise LLMClientError(
            f"LLM request failed for model {self.model} after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    def _log_call(
        self,
        user_prompt: str,
        attempts: int,
        duration_s: float,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Append one JSONL record for this call's final outcome. No-op if log_path is unset.

        Logging must never break ingestion — filesystem errors are swallowed.
        """
        if self.log_path is None:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model": self.model,
            "host": self.host,
            "prompt_chars": len(user_prompt),
            "duration_ms": round(duration_s * 1000),
            "attempts": attempts,
            "success": success,
            "error": error,
        }
        with contextlib.suppress(OSError):
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")

    def extract_structured(self, raw_text: str, context: str = "") -> str:
        """Extract structured OKF markdown from raw OCR or document text."""
        system_prompt = load_extraction_prompt()
        user_prompt = f"Context: {context}\n\nRaw content/OCR:\n{raw_text}{DEFAULT_EXTRACTION_USER_SUFFIX}"
        return self.chat(system_prompt, user_prompt)

    def summarize_sections(self, merged_sections: str) -> str:
        """Synthesize a short orientation summary (+ optional mermaid timeline) for a folder aggregate."""
        system_prompt = load_folder_summary_prompt()
        return self.chat(system_prompt, merged_sections)
