# smart-okf — Agent Instructions

**Agent guides:** [`AGENT_GUIDES.md`](AGENT_GUIDES.md) — coding standards, Python style, system design

Local-first OKF knowledge base: co-located Markdown companions next to sensitive documents, local LLM extraction, Honcho-inspired reasoning (store → derive → dream → query).

## Architecture

```
Document folders (local storage)
        ↓ watcher / manual ingest
app/services/ingest.py  →  text_extraction  →  llm_client  →  OKF .md
        ↓ (planned)
KB manager, enrichment, derive/dream, search, API, MCP
        ↓
Humans browse folders · agents via ripgrep / API / MCPJungle
```

## Module map (current)

| Path | Role |
|------|------|
| `app/models/okf.py` | `OKFFrontmatter`, `OKFDocument` |
| `app/constants.py` | Shared defaults |
| `app/types.py` | Type aliases (`RelativePath`, `FrontmatterPatch`, …) |
| `app/exceptions.py` | `LLMClientError`, `DocumentIngestError` |
| `app/services/ports.py` | Protocols (`ReviewQueuePort`) |
| `app/services/ingest.py` | Folder + file ingest |
| `app/services/llm_client.py` | Ollama chat + extraction |
| `app/services/text_extraction.py` | PDF text (images: broken until PR 3a) |
| `app/services/prompts.py` | Load prompt markdown |
| `app/ui/streamlit_app.py` | Skeleton UI |
| `scripts/ingest_folder.py` | CLI wrapper |
| `prompts/` | LLM system prompts |
| `docs/DESIGN.md` | Phase 0–3 system design + PR plan |

## Dev commands

```bash
uv sync --group dev

# Lint / types / tests
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q

# Ingest test folder
uv run python scripts/ingest_folder.py /path/to/docs

# Streamlit UI
uv run streamlit run app/ui/streamlit_app.py
```

## Environment

| Variable | Default |
|----------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` |
| `DEFAULT_MODEL` | `qwen2.5:3b` (see `DEFAULT_LLM_MODEL` in constants) |

## Key conventions

- OKF markdown: YAML frontmatter + body; `source` provenance required
- Co-located companions: `file.pdf` → `file.md`
- Immutable ingest defaults via `apply_ingest_defaults()` + `model_copy`
- Implementation order: follow PR plan in `docs/DESIGN.md`

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