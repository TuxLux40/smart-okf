"""LLM Client wrapper for your local backend (Ollama, llama.cpp, etc.).

Configure via env or config. Supports chat/completions for extraction and reasoning.
"""

import os
from typing import Optional, List, Dict, Any
import ollama  # pip install ollama; or replace with llama-cpp-python / requests to your endpoint

class LLMClient:
    def __init__(self, 
                 model: str = "qwen2.5:3b",  # Small dedicated model recommended for pipeline
                 host: Optional[str] = None,  # e.g. http://localhost:11434 for Ollama
                 temperature: float = 0.3,
                 max_tokens: int = 2048):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.temperature = temperature
        self.max_tokens = max_tokens
        # For llama.cpp or other backends, add conditional init here

    def chat(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Simple chat interface. Returns assistant response text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            # Ollama example
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                }
            )
            return response['message']['content'].strip()
        except Exception as e:
            # Fallback or error handling for other backends
            print(f"LLM error: {e}")
            return f"[LLM Error] {str(e)}"

    def extract_structured(self, raw_text: str, context: str = "") -> str:
        """Convenience for extraction tasks. Load prompt from file or hardcode."""
        from pathlib import Path
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "extraction_system.md"
        system = prompt_path.read_text() if prompt_path.exists() else "You are an expert at extracting durable facts into OKF format."
        user = f"Context: {context}\n\nRaw content/OCR:\n{raw_text}\n\nOutput only valid OKF markdown with frontmatter and structured body."
        return self.chat(system, user)

    # Add methods for reasoning passes (derive, dream) similarly

# Usage:
# client = LLMClient(model="your-small-model")
# result = client.extract_structured(ocr_text, "genealogy record")
