# smart-okf — Agent Instructions

**Agent guides:** [`AGENT_GUIDES.md`](AGENT_GUIDES.md) — coding standards, Python style, system design

Local-first OKF knowledge base: co-located Markdown companions next to sensitive documents, local LLM extraction, Honcho-inspired reasoning (store → derive → dream → query).

## Architecture

```
Document folders (local storage)
        ↓ manual or cron-scheduled ingest (incremental via source_hashes)
app/services/ingest.py  →  text_extraction (+ in-place OCRmyPDF)  →  llm_client  →  one OKF .md per folder
        ↓
Humans browse folders · agents query via the smart-okf skill + ripgrep
```

## Module map (current)

| Path | Role |
|------|------|
| `app/models/okf.py` | `OKFFrontmatter`, `OKFDocument` |
| `app/constants.py` | Shared defaults |
| `app/types.py` | Type aliases (`RelativePath`, `FrontmatterPatch`, …) |
| `app/exceptions.py` | `LLMClientError`, `DocumentIngestError` |
| `app/services/ports.py` | Protocols (`ReviewQueuePort`) |
| `app/services/ingest.py` | Per-folder aggregate ingest (non-recursive, hash-incremental) |
| `app/services/llm_client.py` | OpenAI-compatible chat + extraction (Ollama, llama.cpp, vLLM, …) |
| `app/services/text_extraction.py` | PDF/docx/eml/csv/xlsx text + in-place OCRmyPDF for scanned PDFs |
| `app/services/prompts.py` | Load prompt markdown |
| `scripts/ingest_folder.py` | CLI wrapper (cron-friendly, --host/--model flags) |
| `prompts/` | LLM system prompts |
| `docs/DESIGN.md` | Phase 0–3 system design + PR plan |
| `docs/OKF_SPEC.md` | OKF file structure, concept format, reserved filenames, type vocabulary |

## Dev commands

```bash
uv sync --group dev

# Lint / types / tests
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q

# Ingest test folder (incremental; unchanged files skipped via source_hashes)
uv run python scripts/ingest_folder.py /path/to/docs --host http://127.0.0.1:1234 --model <model>


```

## Environment

| Variable | Default |
|----------|---------|
| `SMART_OKF_LLM_HOST` | `http://localhost:11434` (any OpenAI-compatible server: Ollama, llama.cpp, vLLM, …) |
| `SMART_OKF_LLM_MODEL` | `qwen2.5:3b` (see `DEFAULT_LLM_MODEL` in constants) |
| `SMART_OKF_LLM_API_KEY` | `not-needed` |

## Key conventions

- OKF markdown: YAML frontmatter + body; provenance required (`sources` + `source_hashes` on aggregates)
- One aggregate per folder: `providers/` → `providers/providers.md` (non-recursive)
- Immutable ingest defaults via `apply_ingest_defaults()` + `model_copy`
- Scope: see 2026-07-17 amendment in `docs/DESIGN.md`; SKILL.md is the agent entry point

---

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.