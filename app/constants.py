"""Shared application constants."""

from pathlib import Path

DEFAULT_LLM_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2048

OKF_VERSION = "0.1"
UNKNOWN_OKF_TYPE = "Unknown"
RELATED_SECTION_HEADING = "## Related"
DEFAULT_LINK_LABEL = "Related"

INDEX_FILENAME = "index.md"
LOG_FILENAME = "log.md"
RESERVED_CONCEPT_FILENAMES = frozenset({INDEX_FILENAME, LOG_FILENAME})
"""Filenames reserved by OKF: directory listing and changelog, never a concept."""

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
EXTRACTION_PROMPT_FILE = "extraction_system.md"
DEFAULT_EXTRACTION_PROMPT = "You are an expert at extracting durable facts into OKF format."
DEFAULT_EXTRACTION_USER_SUFFIX = "\n\nOutput only valid OKF markdown with frontmatter and structured body."

SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".txt"})
TEXT_FILE_ENCODING = "utf-8"
