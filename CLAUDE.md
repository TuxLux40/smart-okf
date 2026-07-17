# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**smart-okf** — local-first OKF (Open Knowledge Format) knowledge base for sensitive documents. Turns folders of PDFs/scans/text into co-located structured Markdown companions (`contract.pdf` → `contract.md`) using a local LLM (Ollama), with no cloud calls. Phase 0 (scaffolding) is current; see roadmap below.

Read [`AGENTS.md`](AGENTS.md) first — it has the module map, dev commands, and key conventions. This file adds Claude-specific notes on top.

## Dev commands

```bash
uv sync --group dev

# Lint / format / type-check / test (run all before considering work done)
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q

# Single test
uv run pytest tests/test_okf.py::test_name -q

# Ingest a folder (manual smoke test)
uv run python scripts/ingest_folder.py /path/to/docs

# Streamlit UI (skeleton)
uv run streamlit run app/ui/streamlit_app.py
```

CI (`.github/workflows/python.yml`) runs the same ruff/mypy/pytest checks on push/PR to `main`.

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

- **OKF documents** (`app/models/okf.py`): `OKFFrontmatter` (Pydantic, `extra: allow`, required `type`, provenance via `source`) + `OKFDocument` (frontmatter + markdown body). `to_markdown`/`from_markdown` round-trip the `---` YAML frontmatter block; `add_link` appends to a `## Related` section in the body.
- **Ingest pipeline** (`app/services/ingest.py`): walks a folder, extracts text (`text_extraction.py` — PDF via pdfplumber; image OCR not yet wired, fails until PR 3a), sends it to `llm_client.py` (Ollama chat, configured via `OLLAMA_HOST`/`DEFAULT_MODEL`), and writes the co-located `.md` companion via the OKF model.
- **Prompts** live in `prompts/*.md` and are loaded by `app/services/prompts.py`; `reasoning_derive.md`/`reasoning_dream.md` exist but are not yet wired into any pipeline (planned "Honcho-inspired" store → derive → dream → query loop).
- **`app/services/ports.py`** defines Protocols (e.g. `ReviewQueuePort`) for pieces not yet implemented — code against the protocol, not a concrete class, when building against planned Phase 1+ components.
- **Immutability convention**: ingest defaults are applied via `apply_ingest_defaults()` + `model_copy` rather than mutating frontmatter in place.
- Everything else (KB manager, folder watcher, `index.md` generation, enrichment gate, FastAPI + MCP tools, Streamlit UI beyond the current skeleton) is planned, not built — check `docs/DESIGN.md` (Phase 0–3 PR plan) before assuming a component exists.

## Code style

Full detail in [`PYTHON_STANDARDS.md`](PYTHON_STANDARDS.md), [`PYTHON_TYPE_SAFETY.md`](PYTHON_TYPE_SAFETY.md), [`CODING_STANDARDS.md`](CODING_STANDARDS.md). Highlights that affect how you should write code here:

- mypy runs in `strict` mode (`disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, etc. — see `pyproject.toml`) for `app/` and `scripts/`; `tests/` is exempt from `disallow_untyped_defs`.
- Use the shared type aliases in `app/types.py` (`RelativePath`, `MarkdownContent`, `OkfTypeName`, `FrontmatterPatch`) instead of raw `str`/`dict` where they apply.
- ruff line-length 120, double quotes, `E501` ignored; lint set is `E W F I B C4 UP SIM`.

## Key conventions

- OKF markdown = YAML frontmatter + body; `source` provenance field is required for anything ingested from a real document.
- Co-located companions only: never write knowledge output anywhere but next to the source file as `<name>.md`.
- Follow the PR-by-PR implementation order in `docs/DESIGN.md` rather than jumping ahead to later-phase features.

## IDE/agent rule duplication

This repo mirrors the same rules across `.cursor/rules/`, `.clinerules/`, `.windsurf/rules/`, `.github/copilot-instructions.md`, `.opencode/AGENTS.md`, and `rules/common/`. If you change a convention (style, type-safety, caveman mode, design process), update the canonical doc (`PYTHON_STANDARDS.md`, `PYTHON_TYPE_SAFETY.md`, `CODING_STANDARDS.md`, or `AGENTS.md`) and keep the IDE-specific copies in sync — don't edit only one.
