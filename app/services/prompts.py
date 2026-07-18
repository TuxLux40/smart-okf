"""Prompt file loading helpers."""

from app.constants import (
    DEFAULT_DREAM_SYNTHESIS_PROMPT,
    DEFAULT_EXTRACTION_PROMPT,
    DEFAULT_FOLDER_SUMMARY_PROMPT,
    DEFAULT_VISION_EXTRACTION_PROMPT,
    DREAM_SYNTHESIS_PROMPT_FILE,
    EXTRACTION_PROMPT_FILE,
    FOLDER_SUMMARY_PROMPT_FILE,
    PROMPTS_DIR,
    VISION_EXTRACTION_PROMPT_FILE,
)


def load_prompt(filename: str, fallback: str = "") -> str:
    """Load a prompt markdown file from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return fallback


def load_extraction_prompt() -> str:
    """Load the system prompt used for OKF extraction."""
    return load_prompt(EXTRACTION_PROMPT_FILE, fallback=DEFAULT_EXTRACTION_PROMPT)


def load_folder_summary_prompt() -> str:
    """Load the system prompt used to synthesize a folder aggregate's top summary."""
    return load_prompt(FOLDER_SUMMARY_PROMPT_FILE, fallback=DEFAULT_FOLDER_SUMMARY_PROMPT)


def load_vision_extraction_prompt() -> str:
    """Load the system prompt used to transcribe + describe images via a vision-capable model."""
    return load_prompt(VISION_EXTRACTION_PROMPT_FILE, fallback=DEFAULT_VISION_EXTRACTION_PROMPT)


def load_dream_synthesis_prompt() -> str:
    """Load the system prompt used by the dream pass to synthesize across folder aggregates."""
    return load_prompt(DREAM_SYNTHESIS_PROMPT_FILE, fallback=DEFAULT_DREAM_SYNTHESIS_PROMPT)
