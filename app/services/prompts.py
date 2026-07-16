"""Prompt file loading helpers."""

from app.constants import DEFAULT_EXTRACTION_PROMPT, EXTRACTION_PROMPT_FILE, PROMPTS_DIR


def load_prompt(filename: str, fallback: str = "") -> str:
    """Load a prompt markdown file from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return fallback


def load_extraction_prompt() -> str:
    """Load the system prompt used for OKF extraction."""
    return load_prompt(EXTRACTION_PROMPT_FILE, fallback=DEFAULT_EXTRACTION_PROMPT)
