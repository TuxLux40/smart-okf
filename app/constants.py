"""Shared application constants."""

from pathlib import Path

DEFAULT_LLM_MODEL = "qwen2.5:3b"
DEFAULT_LLM_HOST = "http://localhost:11434"
"""Any OpenAI-compatible chat completions server: Ollama, llama.cpp server, vLLM, OpenAI, etc."""
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2048

OKF_VERSION = "0.1"
UNKNOWN_OKF_TYPE = "Unknown"
RELATED_SECTION_HEADING = "## Related"
DEFAULT_LINK_LABEL = "Related"

FOLDER_SUMMARY_OKF_TYPE = "FolderSummary"
"""Frontmatter `type` for the one aggregate concept written per folder (non-recursive)."""

FOLDER_INDEX_OKF_TYPE = "FolderIndex"
"""Frontmatter `type` for a roll-up index: a parent folder that has subfolders with
aggregates but no directly-contained documents of its own. Findbuch-Prinzip — it links
down to child aggregates without duplicating their content, so it carries no `sources`
(unlike FolderSummary). Excluded from the `dream` pass (navigation, not content)."""

ROLLUP_HEADING = "## Untergeordnete Ordner"
"""Body section listing links to child-folder aggregates. Injected into a folder's
FolderSummary aggregate when it has subfolders, or the whole body of a FolderIndex."""

TRANSCRIPTS_DIR_NAME = ".okf-transcripts"
"""Hidden root-level folder mirroring the tree with full raw extracted text per source file."""

FACTS_DIR_NAME = ".okf-facts"
"""Hidden root-level folder mirroring the tree with one derived-facts `.md` per source file,
written only when `derive_per_file` is enabled. The facts also live in the folder aggregate;
this is the opt-in per-document artifact for callers who want it."""

INDEX_FILENAME = "index.md"
LOG_FILENAME = "log.md"
RESERVED_CONCEPT_FILENAMES = frozenset({INDEX_FILENAME, LOG_FILENAME})
"""Filenames reserved by OKF: directory listing and changelog, never a concept."""

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
EXTRACTION_PROMPT_FILE = "extraction_system.md"
DEFAULT_EXTRACTION_PROMPT = "You are an expert at extracting durable facts into OKF format."
DEFAULT_EXTRACTION_USER_SUFFIX = "\n\nOutput only valid OKF markdown with frontmatter and structured body."

FOLDER_SUMMARY_PROMPT_FILE = "folder_summary.md"
DEFAULT_FOLDER_SUMMARY_PROMPT = (
    "Write a 2-5 sentence orientation summary of the documents below, in their language. "
    "Only add a mermaid timeline if there are 3+ clearly sequential dated events."
)

OCR_LANGUAGES = "deu+eng"
"""Tesseract language packs used by OCRmyPDF for scanned PDFs."""

CHUNK_CHAR_THRESHOLD = 8_000
"""Character budget, not token — the pipeline is model-agnostic (qwen/gemma/llama all
tokenize differently), so exact token counting would need a specific tokenizer per model."""

LLM_LOG_FILENAME = ".okf-llm-log.jsonl"
"""Hidden root-level JSONL log of every LLM call: model, duration, retries, success."""

SYNTHESIS_OKF_TYPE = "Synthesis"
"""Frontmatter `type` for the root-level cross-folder dream synthesis document."""

SYNTHESIS_FILENAME = "synthesis.md"
"""Root-level output of the dream pass: matters, conflicts, patterns, open actions."""

MATTER_OKF_TYPE = "Matter"
"""Frontmatter `type` for a dedicated per-matter concept file (R2): one persistent, hash-
incremental file per cross-folder matter group, linking the aggregates that share a
reference number. Distinct from `Synthesis`, which is the whole-tree map."""

MATTERS_DIR_NAME = "matters"
"""Root-level, non-hidden folder holding one `.md` per matter group — a real user-facing
concept (unlike `.okf-transcripts/`), so it stays visible."""

DREAM_SYNTHESIS_PROMPT_FILE = "dream_synthesis.md"
DEFAULT_DREAM_SYNTHESIS_PROMPT = (
    "You synthesize a digest of folder aggregates into one cross-folder report with exactly "
    "these markdown sections: '## Matters', '## Conflicts', '## Patterns', '## Open actions'. "
    "Cite aggregate paths for every claim; keep identifiers verbatim; body only, no frontmatter."
)

DREAM_MATTER_PROMPT_FILE = "dream_matter.md"
DEFAULT_DREAM_MATTER_PROMPT = (
    "You investigate one candidate cross-folder matter (aggregates sharing a reference "
    "number) using their full text. Output exactly three sections: '### Matter' (dense "
    "paragraph, every identifier verbatim), '### Conflicts' (contradictions, cite both "
    "sides), '### Actions' (concrete next steps). Cite aggregate paths for every claim."
)

VISION_EXTRACTION_PROMPT_FILE = "vision_extraction.md"
DEFAULT_VISION_EXTRACTION_PROMPT = (
    "Transcribe all legible text in this image verbatim, including handwriting and numbers. "
    "Then briefly describe the scene (setting, objects, what kind of document/photo this is)."
)

FACT_VERIFICATION_PROMPT_FILE = "fact_verification.md"
DEFAULT_FACT_VERIFICATION_PROMPT = (
    "You verify that an extraction accurately reflects its source. Given SOURCE TEXT and "
    "EXTRACTED MARKDOWN, respond with exactly 'OK' if every fact in the extraction is "
    "actually present in the source and nothing is fabricated, templated, or repeated, or "
    "'FLAGGED: <short reason>' otherwise. Be strict: every extracted fact must be traceable "
    "to the source text."
)

VERIFICATION_FLAGGED_MARKER = "FLAGGED"
"""Prefix the verifier responds with when an extraction doesn't hold up — everything after
the marker (colon/dash-stripped) becomes the human-readable reason."""

IMAGE_DOCUMENT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
"""Standalone images: OCRed via tesseract by default, or via a vision-capable chat model
(handwriting + scene description) when `vision_model` is configured."""

SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".pdf", ".txt", ".docx", ".eml", ".csv", ".xlsx"}) | IMAGE_DOCUMENT_SUFFIXES
TEXT_FILE_ENCODING = "utf-8"
