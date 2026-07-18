# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**smart-okf** — local-first OKF (Open Knowledge Format) knowledge base for sensitive documents, packaged as an agent skill (`SKILL.md` at repo root). Turns document folders into one aggregate Markdown file per folder (`providers/` → `providers/providers.md`, non-recursive) using any OpenAI-compatible LLM (LM Studio, llama.cpp, Ollama, vLLM), with no cloud calls required. No webapp, no daemons — agents invoke the skill, cron runs the same CLI.

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

# Ingest a folder (incremental — unchanged files skipped via source_hashes)
uv run python scripts/ingest_folder.py /path/to/docs --host http://127.0.0.1:1234 --model <model>


```

CI (`.github/workflows/python.yml`) runs the same ruff/mypy/pytest checks on push/PR to `main`.

## Architecture

```
Document folders (local storage)
        ↓ manual or cron-scheduled ingest (incremental via source_hashes)
app/services/ingest.py  →  text_extraction (+ in-place OCRmyPDF)  →  llm_client  →  one OKF .md per folder
        ↓
Humans browse folders · agents query via the smart-okf skill + ripgrep
```

- **OKF documents** (`app/models/okf.py`): `OKFFrontmatter` (Pydantic, `extra: allow`, required `type`, provenance via `source`) + `OKFDocument` (frontmatter + markdown body). `to_markdown`/`from_markdown` round-trip the `---` YAML frontmatter block; `add_link` appends to a `## Related` section in the body.
- **Ingest pipeline** (`app/services/ingest.py`): walks a folder tree; per directory (non-recursive) extracts text from each supported file (`text_extraction.py` — pdfplumber plus in-place OCRmyPDF for scanned PDFs; `.docx`/`.eml`/`.csv`/`.xlsx` native; standalone images skipped), runs one LLM extraction per changed file (`llm_client.py`, any OpenAI-compatible server via `SMART_OKF_LLM_HOST`/`SMART_OKF_LLM_MODEL`), and merges results into one `FolderSummary` aggregate per folder. Incremental: `source_hashes` frontmatter (SHA-256 per source) lets unchanged files reuse their existing aggregate section without an LLM call; in-place OCR rewrites the PDF, so hashes are recomputed after extraction.
- **Prompts** live in `prompts/*.md` and are loaded by `app/services/prompts.py`; `reasoning_derive.md`/`reasoning_dream.md` exist but are not yet wired into any pipeline (planned "Honcho-inspired" store → derive → dream → query loop).
- **`app/services/ports.py`** defines Protocols (e.g. `ReviewQueuePort`) for pieces not yet implemented — code against the protocol, not a concrete class, when building against planned Phase 1+ components.
- **Immutability convention**: ingest defaults are applied via `apply_ingest_defaults()` + `model_copy` rather than mutating frontmatter in place.
- Everything else (enrichment gate, derive/dream reasoning) is optional/later, not built — see the 2026-07-17/18 scope amendments at the top of `docs/DESIGN.md` before assuming a component exists. Remote (non-filesystem) agent access is undecided between a git remote and an MCP server (roadmap R1) — FastAPI specifically is cut, not a live option; don't resurrect it, the watcher, per-file companions, or Streamlit either. `index.md` generation was dropped as redundant, not deferred — see `docs/OKF_SPEC.md`'s "Index files" section.

## Code style

Full detail in [`PYTHON_STANDARDS.md`](PYTHON_STANDARDS.md), [`PYTHON_TYPE_SAFETY.md`](PYTHON_TYPE_SAFETY.md), [`CODING_STANDARDS.md`](CODING_STANDARDS.md). Highlights that affect how you should write code here:

- mypy runs in `strict` mode (`disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, etc. — see `pyproject.toml`) for `app/` and `scripts/`; `tests/` is exempt from `disallow_untyped_defs`.
- Use the shared type aliases in `app/types.py` (`RelativePath`, `MarkdownContent`, `OkfTypeName`, `FrontmatterPatch`) instead of raw `str`/`dict` where they apply.
- ruff line-length 120, double quotes, `E501` ignored; lint set is `E W F I B C4 UP SIM`.

## Key conventions

- OKF markdown = YAML frontmatter + body; provenance is required for ingested content (`sources` + `source_hashes` on aggregates, `source` on single-document concepts). Format rules: `docs/OKF_SPEC.md`.
- Knowledge output lives inside the document folders (one aggregate per folder); never write it anywhere else.
- `index.md`/`log.md` are reserved OKF filenames — never concept/aggregate names.

## IDE/agent rule duplication

This repo mirrors the same rules across `.cursor/rules/`, `.clinerules/`, `.windsurf/rules/`, `.github/copilot-instructions.md`, `.opencode/AGENTS.md`, and `rules/common/`. If you change a convention (style, type-safety, caveman mode, design process), update the canonical doc (`PYTHON_STANDARDS.md`, `PYTHON_TYPE_SAFETY.md`, `CODING_STANDARDS.md`, or `AGENTS.md`) and keep the IDE-specific copies in sync — don't edit only one.
