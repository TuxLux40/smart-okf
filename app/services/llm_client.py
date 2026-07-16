"""LLM client wrapper for local backends (Ollama, llama.cpp, etc.)."""

import os
from typing import Any

import ollama

from app.constants import (
    DEFAULT_EXTRACTION_USER_SUFFIX,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OLLAMA_HOST,
)
from app.exceptions import LLMClientError
from app.services.prompts import load_extraction_prompt


class LLMClient:
    """Chat client for extraction and reasoning tasks against a local LLM."""

    def __init__(
        self,
        model: str = DEFAULT_LLM_MODEL,
        host: str | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Run a chat completion and return the assistant response text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                },
            )
            content = response["message"]["content"]
            return str(content).strip()
        except Exception as error:
            raise LLMClientError(f"LLM request failed for model {self.model}") from error

    def extract_structured(self, raw_text: str, context: str = "") -> str:
        """Extract structured OKF markdown from raw OCR or document text."""
        system_prompt = load_extraction_prompt()
        user_prompt = f"Context: {context}\n\nRaw content/OCR:\n{raw_text}{DEFAULT_EXTRACTION_USER_SUFFIX}"
        return self.chat(system_prompt, user_prompt)
