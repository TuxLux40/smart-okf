# Handoff for Claude (second review — fable)

**Author of this pass:** Grok (user asked for review-fix cleanup + commit after Claude's
prior session). **Goal of your run:** re-review with fable when usage resets; verify claims
vs code; do **not** re-litigate settled product decisions without user confirmation.

## Core purpose (locked — user-confirmed 2026-07-19)

> **Aggregates = library of atomic facts.**  
> **Synthesis = librarian that notices the same story, fights, and next steps.**  
> **Honcho-as-architecture is out. Honcho-as-inspiration for smarter passes over your MDs is in.**

Do not reverse this framing. Retrieval ladder is how agents use the library. R2/R2b is the librarian track. Do not port Honcho infra; do not claim extract-only is “all the reasoning.”

## Settled product decisions (do not reverse without asking)

| Decision | Rationale |
|----------|-----------|
| **Core purpose above** | Library + librarian; Honcho goals not stack |
| **marker external, default on, `--no-marker` opt-out** | Layout PDFs; external install, not pip dep |
| **Orchestrator ≠ extractor (degree of privacy)** | Script extracts; local default; hosted OK with `allow_remote_llm`; query prefers MD |
| **JSONL LLM log** | Ops only, not knowledge |
| **Private git remote (R1)** | Web agents on aggregates |
| **Skill is publishable** | No personal case names in SKILL/README |
| **Cron over watcher; one aggregate per folder non-recursive** | User architecture |
| **git = timeline; MD = current truth** | IDs in commits + bodies |
| **Retrieval ladder mandatory** | Whole tree → MD → transcripts → git |

## Known bug / gap: orphan aggregates on full delete

**Confirmed behavior (as of handoff update):** when a *source file* is deleted and the folder still has other supported docs, re-ingest rebuilds from disk only — that file’s section and `source_hashes` entry go away. **Gap:** if a folder’s last supported file is removed, `_ingest_directory` hits `if not files: return` and **leaves the old `<folder>/<folder>.md` on disk** (stale hashes + stale facts). Also: aggregate **tags** from deleted docs can linger; **`.okf-transcripts/`** sidecars for deleted sources are not pruned.

**Fix if implementing (user wants this tracked):** when `files` is empty after a scan, delete or clear the aggregate if it exists (and optionally prune orphan transcripts for missing sources). Add a regression test. Do not treat as intentional design.

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
6. **Orphan aggregate when last file in a folder is deleted** — see gap above; confirm and/or fix.
7. **DESIGN.md body** — large historical FastAPI/Streamlit/MCP sections still below amendments; doc drift risk.
8. **No personal data** in published skill paths.
9. **Tests** — `uv run pytest -q`, `mypy`, `ruff` should be green after this commit.

## Commands

```bash
cd /home/oliver/Projects/smart-okf
uv sync --group dev
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q
```

## Out of scope unless user asks

- Root meta-markdowns / cross-folder re-reason (**R2** — only when git batch correlation is not enough; see git vs MD principle above)
- Verbosity valve (R3), semantic dupes (R4), cron install CLI (R5), Docling backend (R6)
- Building a smart-okf MCP server (git remote is the decided remote path)
- Re-litigating personal legal/benefits cases in chat — tooling only; **no personal case names in published skill/README**

---

## Product backlog (Claude — after review or when asked)

Ordered roughly by user priority. Do **not** turn the whole skill into a genealogy product.

### Priority re-evaluation (user 2026-07-19) — clarified

- User wants **all the reasoning they can get**. They thought Honcho was *superseded*, not unwanted.
- **Superseded:** porting Honcho’s stack (derive/dream *product*, peers, queues).
- **Not superseded:** dream-class *goals* — conflicts, patterns, cross-folder matter, actions — on top of aggregates. Roadmap **R2 / R2b** (matter + synthesis). Keep `prompts/reasoning_*.md` as seed prompts, not “fossils to ignore.”
- **Aggregates** = extract/compile (necessary; form-fill facts). **Not** a substitute for whole-KB synthesis.
- Also invest: retrieval pipeline, automated re-ingest, date-range extraction (P0).
- Privacy = spectrum (README).

### P0 — Motivating failure mode (pre-distill form-critical facts)

**User context (do not put personal case names in SKILL/README):** A prior Mistral Vibe session filling a German social-benefits form repeatedly failed to pull the right **date ranges** (e.g. “from … to …” for wage-replacement benefits, Bewilligungszeitraum on notices). Agents re-scanned folders each time and got worse under context pressure. **That is why pre-distilled OKF aggregates + transcripts exist** — exact periods, IDs, and amounts must be greppable without re-deriving from PDFs every query.

**Work:**

1. **Default extraction prompt** (`prompts/extraction_system.md`): raise priority of *period* facts — every explicit date range, Leistungszeitraum, Bewilligt von/bis, Vertragsbeginn/-ende, Gültig ab/bis — as atomic bullets with labels and source context. Prefer ISO-like or unambiguous German dates. Already strong on IDs/amounts; **date ranges were the live gap**.
2. Keep **transcript fallback** mandatory when ranges are partial.
3. Optional later: dedicated `## Zeiträume / Periods` body section convention for form-heavy docs.

### P1 — Optional genealogy **addon** (not the core skill)

Genealogy is a strong vertical (person/place/event linking) but must stay an **addon**, not rebrand smart-okf.

| Layer | What |
|-------|------|
| **Default mode** | Share genealogy’s *discipline*: names, places, exact dates/ranges, joinable IDs — for *all* personal docs |
| **Addon** | Optional prompt file e.g. `prompts/extraction_genealogy.md` + SKILL subsection or `docs/ADDONS.md` / config flag `extraction_profile: default \| genealogy` |
| **Addon extras** | Person/place/event bullets; optional later person-concept pages; vision for handwritten registers — only when profile=genealogy |
| **Must not** | Replace SKILL description with “genealogy skill”; hard-code family-tree ontology into default ingest |

### P2 — Marketing concept for **max virality** (docs/strategy, not code first)

User asked this on the todo list. Deliverable: a short **marketing / positioning concept** (could live as `docs/MARKETING.md` draft, uncommitted until user okays publish tone):

- Hook that is demoable in ≤60s (before/after: agent only opens one folder vs whole-tree ladder)
- One-liner vs Paperless / RAG / “just Claude on PDFs”
- Fake sample tree (synthetic documents — no real PII) for screenshots
- Channels: agent-skill lists, OKF/Marie Haynes/Karpathy-wiki discourse, local-LLM Reddit/HN
- Why not caveman-meme: depth vs costume — still design a *shareable* slice without dumbing down privacy
- CTA: skill install + first ingest on sample folder

### P3 — Already tracked gaps

- Orphan aggregate when last file in folder deleted
- Exit codes when skips > 0
- DESIGN.md historical body drift

---

## Karpathy LLM wiki vs OKF (reference for docs)

| | **Karpathy LLM wiki** | **OKF (Google)** |
|--|----------------------|------------------|
| What | **Pattern / idea** (gist): raw sources + LLM-maintained markdown wiki + schema (CLAUDE.md); ingest/query/lint | **Standard / format**: markdown + YAML frontmatter conventions so any agent can consume any bundle |
| Origin | [karpathy/llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | [knowledge-catalog OKF SPEC](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md); Google blog frames OKF as formalizing the LLM-wiki pattern |
| Core insight | Don’t re-RAG raw docs every question — **compile** a compounding wiki | Same files should be **interoperable** across tools/agents |
| smart-okf | Implements the pattern (raw docs, distilled MD, skill as schema, git, lint-ish retrieval ladder) | Uses OKF-shaped frontmatter + FolderSummary aggregates as the portable on-disk form |

**One line:** LLM wiki = *how you work*; OKF = *how the files are shaped so others can work too*.

---

## Stop condition for your review

Post findings ordered by severity. Prefer structural/correctness over nits. If approving, say what residual risk remains. If blocking, list minimal fixes only.

After review (or if user skips straight to build): pick from **Product backlog** above; default extraction date-range hardening is the highest-ROI code change tied to the real form-filling failure mode.
