"""LLM client for any OpenAI-compatible chat completions backend.

Works unmodified against Ollama, llama.cpp's `llama-server`, vLLM, LM Studio, or hosted
OpenAI-compatible APIs — anything serving `POST {host}/v1/chat/completions`.
"""

import base64
import contextlib
import json
import mimetypes
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.constants import (
    DEFAULT_EXTRACTION_USER_SUFFIX,
    DEFAULT_LLM_HOST,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
)
from app.exceptions import LLMClientError
from app.services.prompts import (
    load_dream_matter_prompt,
    load_dream_synthesis_prompt,
    load_extraction_prompt,
    load_fact_verification_prompt,
    load_folder_summary_prompt,
    load_vision_extraction_prompt,
)

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
        model: str | None = None,
        host: str | None = None,
        api_key: str | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        log_path: Path | None = None,
        vision_model: str | None = None,
        content_language: str | None = None,
    ) -> None:
        self.model: str = model if model is not None else os.getenv("SMART_OKF_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.host: str = host if host is not None else os.getenv("SMART_OKF_LLM_HOST", DEFAULT_LLM_HOST)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.log_path = log_path
        self.vision_model: str | None = (
            vision_model if vision_model is not None else os.getenv("SMART_OKF_VISION_MODEL")
        )
        self.content_language: str | None = (
            content_language if content_language is not None else os.getenv("SMART_OKF_CONTENT_LANGUAGE")
        )
        self._client = OpenAI(
            base_url=_as_v1_base_url(self.host),
            api_key=api_key or os.getenv("SMART_OKF_LLM_API_KEY", "not-needed"),
        )

    def _localized(self, system_prompt: str) -> str:
        """Append a language directive to `system_prompt` when `content_language` is set.

        Only used by callers that generate free prose (extraction, summaries, dream). Never
        applied to `verify_facts` (its output is a fixed OK/FLAGGED verdict, not prose) — see
        `content_language`'s docstring in `app/config.py` for what this does and doesn't cover.
        """
        if not self.content_language:
            return system_prompt
        return (
            f"{system_prompt}\n\nWrite your own generated framing text — titles, descriptions, "
            f"tags, orientation summaries, dream synthesis prose — in {self.content_language}, "
            f"regardless of the source document's language. This does not apply to facts you "
            f"extract from a source document: keep those faithful to the source's own wording "
            f"and language, never translate them."
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
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._complete(messages, self.model, user_prompt, temperature=temperature, max_tokens=max_tokens)

    def describe_image(self, image_path: Path, *, context: str = "") -> str:
        """Transcribe (including handwriting) and briefly describe an image via a vision model.

        Requires `vision_model` to be configured (`SMART_OKF_VISION_MODEL` or the constructor
        arg) — there's no reliable way to detect vision capability from a model name alone, so
        this is explicit opt-in rather than an auto-detected fallback.
        """
        if self.vision_model is None:
            raise LLMClientError("describe_image called without a configured vision_model")
        system_prompt = load_vision_extraction_prompt()
        image_bytes = image_path.read_bytes()
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        user_text = f"Image: {context}" if context else "Image"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        return self._complete(messages, self.vision_model, user_text, payload_bytes=len(image_bytes))

    def _complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        log_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        payload_bytes: int | None = None,
    ) -> str:
        """Run a chat completion against `model` with retry/backoff and call logging."""
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                )
                content = (response.choices[0].message.content or "").strip()
                self._log_call(
                    model,
                    log_prompt,
                    attempt + 1,
                    time.monotonic() - started,
                    success=True,
                    payload_bytes=payload_bytes,
                )
                return content
            except Exception as error:
                last_error = error
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        self._log_call(
            model,
            log_prompt,
            _MAX_ATTEMPTS,
            time.monotonic() - started,
            success=False,
            error=str(last_error),
            payload_bytes=payload_bytes,
        )
        raise LLMClientError(
            f"LLM request failed for model {model} after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    def _log_call(
        self,
        model: str,
        user_prompt: str,
        attempts: int,
        duration_s: float,
        *,
        success: bool,
        error: str | None = None,
        payload_bytes: int | None = None,
    ) -> None:
        """Append one JSONL record for this call's final outcome. No-op if log_path is unset.

        Logs the model actually used for this call (extraction vs vision), not only
        `self.model`; `payload_bytes` records binary attachment size (images) that
        `prompt_chars` can't see. Logging must never break ingestion — filesystem errors
        are swallowed.
        """
        if self.log_path is None:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model": model,
            "host": self.host,
            "prompt_chars": len(user_prompt),
            "payload_bytes": payload_bytes,
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
        system_prompt = self._localized(load_extraction_prompt())
        user_prompt = f"Context: {context}\n\nRaw content/OCR:\n{raw_text}{DEFAULT_EXTRACTION_USER_SUFFIX}"
        return self.chat(system_prompt, user_prompt)

    def summarize_sections(self, merged_sections: str) -> str:
        """Synthesize a short orientation summary (+ optional mermaid timeline) for a folder aggregate."""
        system_prompt = self._localized(load_folder_summary_prompt())
        return self.chat(system_prompt, merged_sections)

    def dream_synthesis(self, digest: str, *, max_tokens: int | None = None) -> str:
        """Cross-folder "dream" pass: synthesize matters/conflicts/patterns/actions from aggregate digests.

        Synthesis output is longer-form than per-document extraction, so callers may raise
        `max_tokens` above the extraction default.
        """
        system_prompt = self._localized(load_dream_synthesis_prompt())
        return self.chat(system_prompt, digest, max_tokens=max_tokens)

    def dream_matter(self, group_text: str, *, max_tokens: int | None = None) -> str:
        """Deep-dive one candidate cross-folder matter using full aggregate text (not digests).

        Only called for candidate groups a cheap non-LLM pre-filter already found sharing a
        reference number (`app/services/matter_grouping.py`) — bounded cost, not O(aggregates).
        """
        system_prompt = self._localized(load_dream_matter_prompt())
        return self.chat(system_prompt, group_text, max_tokens=max_tokens)

    def verify_facts(self, source_text: str, extracted_markdown: str, *, max_tokens: int | None = None) -> str:
        """Ask whether `extracted_markdown` is traceable to `source_text` — "OK" or "FLAGGED: <reason>".

        Mandatory verification step, not a second extraction: bounded input (the source text
        already read for the original extraction call, not re-read/re-OCR'd) and a one-line
        output, so the cost is a small, fixed fraction of the extraction call it checks.
        """
        system_prompt = load_fact_verification_prompt()
        user_prompt = f"SOURCE TEXT:\n{source_text}\n\nEXTRACTED MARKDOWN:\n{extracted_markdown}"
        return self.chat(system_prompt, user_prompt, max_tokens=max_tokens)

    def available_models(self) -> list[str]:
        """Model ids the server at `self.host` currently reports (`GET /v1/models`).

        LM Studio/Ollama/llama.cpp serve whatever model happens to be loaded regardless
        of what a client asks for by name — pointing `self.model` at a config value does
        not make the server load it. Used by `confirm_model_available` to catch a
        silently swapped/stale model before it degrades a whole ingest run.
        """
        try:
            response = self._client.models.list()
        except Exception as error:
            raise LLMClientError(f"Could not reach {self.host} to list loaded models: {error}") from error
        return [item.id for item in response.data]

    def confirm_model_available(self) -> None:
        """Raise `LLMClientError` if `self.model` is not currently loaded at `self.host`.

        Observed failure this guards against: config says `google/gemma-4-e4b`, but
        LM Studio actually had `llama-3.2-1b-instruct` loaded (then later
        `openai/gpt-oss-20b` after a UI model swap) — every extraction that run used
        whatever was loaded, silently, with no error anywhere. A 1B model hallucinated
        dates and domain terms in otherwise-plausible-looking aggregates. Call once per
        configured client before a real ingest/dream run, not per-file.
        """
        available = self.available_models()
        if self.model not in available:
            raise LLMClientError(
                f"Configured model {self.model!r} is not loaded at {self.host} "
                f"(server currently reports: {', '.join(available) if available else 'no models'}). "
                "Load the configured model in your LLM server, fix llm_model/dream_model/verify_model "
                "in config, or pass --allow-model-mismatch to proceed anyway (not recommended — "
                "extraction quality is not guaranteed with an unverified model)."
            )
