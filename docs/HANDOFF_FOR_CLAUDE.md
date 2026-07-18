# Handoff for Claude (second review — fable)

**Author of this pass:** Grok (user asked for review-fix cleanup + commit after Claude's
prior session). **Goal of your run:** re-review with fable when usage resets; verify claims
vs code; do **not** re-litigate settled product decisions without user confirmation.

## Settled product decisions (do not reverse without asking)

| Decision | Rationale |
|----------|-----------|
| **marker external, default on, `--no-marker` opt-out** | User wants layout-aware PDFs; install via `pipx install marker-pdf` at onboarding — **not** a pip dep of this MIT skill |
| **Orchestrator ≠ extractor** | Script is subprocess; local model always extracts; cloud agent must not be the OCR path |
| **JSONL LLM log** | Homegrown langfuse *substitute*; operational telemetry, not knowledge; usually gitignored |
| **Private git remote for web agents (R1)** | Gitea/GitLab/… push of aggregates; MCP optional glue on a *clone*, not the primary product |
| **Skill is publishable** | No personal case names (e.g. Grundsicherung) in SKILL.md / public docs |
| **Cron over watcher; one aggregate per folder non-recursive** | User-driven architecture |

## What landed since commit `4541acd` (and cleanup on top)

### Features (Claude WIP + Grok finish)

- Vision image path: `LLMClient.describe_image` + `prompts/vision_extraction.md` + `--vision-model`
- Marker default **on** (opt-out); CLI `log_path` wired so JSONL actually writes on real runs
- `LLMClient.model` / `vision_model` env fallbacks; `_log_call` records **actual model used**
- README/SKILL: orchestrator vs extractor, why scripts exist, JSONL vs git, remote git access
- DESIGN R1 marked **decided: private git**

### Review cleanup (this commit)

- **Dropped chonkie** — pure character-budget splitter in `app/services/chunking.py` (stdlib only)
- **`ExtractionOptions`** — `app/services/extraction_options.py`; no more `use_marker=` parade through every signature
- **Transcript backfill** uses `LIGHT_EXTRACTION` (never marker / PyTorch cold-start)
- **Marker failures** include stderr snippets
- **`merge_chunk_documents`** fills empty first-chunk title/description/source from later chunks; tags union
- Dead **`scripts/onboard.py`** refs removed (error string + example yaml)
- FrontmatterPatch typing allows tag lists

## Map: library ↔ feature (for claim checks)

| Thing | Source |
|-------|--------|
| Chunk long text | **stdlib** `chunking.py` (chonkie was tried then removed) |
| JSONL call log | Homegrown in `llm_client.py` (langfuse rejected) |
| PDF layout | External **marker** subprocess only |
| Scanned PDF rewrite | OCRmyPDF path when `--no-marker` |
| Vision handwriting/scene | Local vision model via OpenAI-compatible API |

## Suggested review focus (fable)

1. **Claims vs code** — especially commit messages, README feature table, SKILL onboarding steps.
2. **Marker default-on** — hard-fail if binary missing: intentional after onboarding; still footgun for bare `uv run` without marker?
3. **Vision double call** (describe → extract_structured) cost / size of base64 images.
4. **Chunk merge quality** — still concat bodies; only fills empty FM fields (not full synthesis).
5. **Exit codes** — skips still may exit 0; cron “green” while files skipped.
6. **DESIGN.md body** — large historical FastAPI/Streamlit/MCP sections still below amendments; doc drift risk.
7. **No personal data** in published skill paths.
8. **Tests** — `uv run pytest -q`, `mypy`, `ruff` should be green after this commit.

## Commands

```bash
cd /home/oliver/Projects/smart-okf
uv sync --group dev
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q
```

## Out of scope unless user asks

- Root meta-markdowns / cross-folder re-reason (R2)
- Verbosity valve (R3), semantic dupes (R4), cron install CLI (R5), Docling backend (R6)
- Building a smart-okf MCP server (git remote is the decided remote path)
- Re-opening E.ON / personal dispute content (tooling only)

## Stop condition for your review

Post findings ordered by severity. Prefer structural/correctness over nits. If approving, say what residual risk remains. If blocking, list minimal fixes only.
