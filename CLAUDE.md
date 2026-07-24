# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**smart-okf** — OKF knowledge base for personal documents, packaged as an agent skill (`SKILL.md`).
**Core purpose:** aggregates = library of atomic facts; synthesis passes = librarian (same story,
conflicts, next steps) inspired by Honcho *reasoning goals*, not Honcho infra; retrieval ladder in
the skill is mandatory. Ingest turns folders into one aggregate MD per folder (non-recursive) via
any OpenAI-compatible LLM (local default). No webapp/daemon — skill + cron CLI.

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
- **Prompts** live in `prompts/*.md`; `dream_synthesis.md` powers the shipped dream pass (`app/services/dream.py` + `scripts/dream.py` → root `synthesis.md`, `type: Synthesis`, hash-incremental). `reasoning_derive.md`/`reasoning_dream.md` remain as seeds for deeper R2 matter passes.
- **`app/services/ports.py`** defines Protocols (e.g. `ReviewQueuePort`) for pieces not yet implemented — code against the protocol, not a concrete class, when building against planned Phase 1+ components.
- **Immutability convention**: ingest defaults are applied via `apply_ingest_defaults()` + `model_copy` rather than mutating frontmatter in place.
- **Four-pass model** (`docs/EVAL_PASSES_AND_GATING.md`, `docs/ARCHIVAL_PRINCIPLES.md`): extract → derive → aggregate (incl. roll-up) → dream. `derive` (facts into the aggregate) and `aggregate` roll-up (`## Subfolders` sections; `type: FolderIndex` for pure parents; finding-aid principle, links not re-summaries) are core/always-on. Gating (`app/services/gating.py`) excludes junk from ingest and eagerly deprioritizes trivial docs out of `dream`; password-protected files → `EncryptedDocumentError`, skipped+logged. `ordering_principle` (provenance/pertinence) tunes matter aggressiveness in `matter_grouping`. `app/services/navigation.py` regenerates a human `README.md` at the root each ingest (never clobbers a hand-written one).
- Per-file artifacts are opt-in only: `derive_per_file` writes `.okf-facts/<file>.md` (facts are always in the aggregate regardless). The old always-on per-file companions and `index.md` generation stay cut/dropped — see `docs/OKF_SPEC.md`.
- Everything else (enrichment gate, Honcho-style reasoning_derive/reasoning_dream prompt passes) is optional/later or deprioritized — see `docs/DESIGN.md` and README roadmap before assuming a component exists. Remote agent access is **private git remote of aggregates** (R1 decided). FastAPI, watcher, Streamlit are cut.

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
