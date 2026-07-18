# smart-okf

[![CI](https://github.com/TuxLux40/smart-okf/actions/workflows/python.yml/badge.svg)](https://github.com/TuxLux40/smart-okf/actions/workflows/python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![OKF v0.1](https://img.shields.io/badge/OKF-v0.1-informational.svg)](docs/OKF_SPEC.md)

**Local-first [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) knowledge base** for sensitive personal documents. Point it at a folder tree — health records, insurance, government correspondence, provider contracts — and it turns every folder into one aggregate Markdown file, extracted by an LLM you run yourself. Nothing leaves your machine, and the originals never move.

Ships as a [Claude Code agent skill](SKILL.md): install it once, and any skill-aware agent with local filesystem access can ingest new documents and answer questions from the knowledge base on request — no server, no daemon, no webapp. Agents *without* local filesystem access (Claude in the browser, etc.) consume the **finished Markdown** via a private git remote — see [Remote access via git](#remote-access-via-git).

---

## Contents

- [Orchestrator vs. extractor](#orchestrator-vs-extractor)
- [Why a script (not “just let the agent extract”)?](#why-a-script-not-just-let-the-agent-extract)
- [Why not just use X?](#why-not-just-use-x)
- [How it works](#how-it-works)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Change tracking](#change-tracking)
- [Remote access via git](#remote-access-via-git)
- [LLM call log (JSONL) — not git](#llm-call-log-jsonl--not-git)
- [Configuration](#configuration)
- [OKF output format](#okf-output-format)
- [Development](#development)
- [Roadmap](#roadmap)
- [Core principles](#core-principles)

## Orchestrator vs. extractor

Two separate roles, easy to conflate:

| Role | Who | Does what | Sees raw PDFs/images? |
|------|-----|-----------|------------------------|
| **Orchestrator** | Claude Code, OpenWebUI/Hermes automation, cron, you | Decides *when* to ingest and *what* to answer; reads `SKILL.md`; runs the CLI; searches finished `.md` files | **No** (by design) |
| **Extractor** | Local model behind `SMART_OKF_LLM_HOST` / `SMART_OKF_LLM_MODEL` (LM Studio, llama.cpp, Ollama, …) | Turns extracted text into structured OKF markdown **inside** `scripts/ingest_folder.py` | **Yes** — only on your machine |

The split is not “cron vs. agent.” The same script serves both. It is “whoever orchestrates” vs. “whichever local model the script always calls for extraction.”

**There is no mode where the orchestrating agent’s own inference *is* the extractor.** The script is a subprocess with no callback into a live agent session. That is intentional:

1. **Privacy** — raw document bytes and full OCR text stay off cloud-hosted orchestrators, even when you drive smart-okf from Claude or another web agent.
2. **Identical behavior** — interactive agent runs and unattended cron runs produce the same files the same way.
3. **Portability of the *knowledge*** — web agents do not re-OCR your NAS; they read portable Markdown you already produced (often via a private git remote — below).

Env vars for the model are about the **extractor**, not “which chat model is talking to you.” The orchestrator can be Claude; the extractor stays local.

## Why a script (not “just let the agent extract”)?

Agents *can* open PDFs and write Markdown by hand for a one-off folder. That does not replace the pipeline as a **system**:

| Need | Pure “agent + instructions” | Script (`scripts/ingest_folder.py`) |
|------|----------------------------|-------------------------------------|
| Privacy of raw docs | Raw text enters the orchestrator’s context | Extractor stays local; orchestrator only sees `.md` / search hits you open |
| Sunday 3am re-ingest | No agent online | Cron runs the same CLI |
| Incremental skip | Easy to forget / re-do everything | SHA-256 `source_hashes` — unchanged files cost zero LLM calls |
| OCR, marker, transcripts, heading demotion | Fragile to re-prompt every time | Owned once, tested |
| Same result for Claude, Hermes, OpenWebUI, cron | Each agent reinvents steps | One tool, one contract |

So the script is not mainly “to make agents type less.” It is the **extractor engine**: deterministic, schedulable, local. The skill (`SKILL.md`) teaches agents how to drive it and how to query the results.

**Portability split:**

- **Most portable for web agents** = finished `.md` aggregates (and optionally a private git remote of them), not “run the whole OCR stack in the browser.”
- **Most portable for knowledge** = plain folders + Markdown + git history — no DB, no smart-okf daemon to keep running just to answer questions.

## Why not just use X?

## Why not just use X?

Mature alternatives exist and are worth trying first:

| Alternative | Good fit if... | Gap |
|---|---|---|
| **[Paperless-ngx](https://docs.paperless-ngx.com/)** | You want mature OCR + full-text search + "Correspondents" (doctors, insurers, ISPs) out of the box | Documents live in its DB, not plain files; no LLM-extracted structured facts |
| **OpenWebUI RAG** | You just want to chat with a folder of PDFs, zero setup | No structured facts, no human-browsable output, no provenance |

Neither combines all three of: LLM-extracted structured facts, files that stay plain Markdown next to the originals (`git clone` + `cat` is all you need to read the whole thing — no DB, no server), and a format any agent can traverse without a bespoke SDK. That combination is smart-okf's reason to exist. If you don't need the git-portable, no-server-required property, Paperless-ngx or OpenWebUI RAG will get you there faster.

## How it works

```
Document folders (local storage)
        │  manual or cron-scheduled ingest
        ▼
text extraction (+ in-place OCR)  →  your LLM  →  one OKF .md per folder
        │
        ▼
Humans browse folders directly · agents query via ripgrep / this skill
```

1. Point smart-okf at a document folder — once, or on a schedule (cron/systemd timer).
2. Each supported file is read: PDFs via external `marker_single` by default (layout-aware;
   opt out with `--no-marker` for `pdfplumber` + in-place OCRmyPDF), `.docx`/`.eml`/`.csv`/`.xlsx`/`.txt`
   natively, images via `tesseract` or an optional vision model.
3. Your **local extractor** LLM structures facts per file into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) markdown — any OpenAI chat-completions server: llama.cpp, LM Studio, Ollama, vLLM. (The orchestrating agent is separate — see above.)
4. Every folder's extractions merge into **one aggregate `.md` in that folder** — non-recursive, a subfolder gets its own separate aggregate — with a synthesized orientation summary on top and full per-file provenance below.
5. Humans browse folders directly; agents query the aggregates via ripgrep, or invoke this skill.

**Where to install tools:** `uv`, system CLIs (`rg`, `tesseract`, `gs`, `marker_single`), and the
LLM server run on the **machine that performs ingest** (usually the one with the GPU/CPU model).
Document roots may live on a NAS/mount; you do **not** need to install PyTorch/marker on the
NAS itself.

## Features

| Capability | Status |
|---|---|
| One aggregate OKF `.md` per folder, non-recursive (`providers/` → `providers/providers.md`) | ✅ |
| PDF, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx`, and image (`.png`/`.jpg`/`.jpeg`) ingest | ✅ |
| Scanned-PDF OCR, embedded in the PDF itself (OCRmyPDF, deu+eng) — runs once, ever | ✅ |
| Standalone image OCR (tesseract, read-only) | ✅ |
| Raw transcript store (`.okf-transcripts/`) — lossless full text, extraction never repeats | ✅ |
| Hash-incremental re-ingest — unchanged files make zero LLM calls | ✅ |
| Synthesized per-folder summary + mermaid timeline for dated events | ✅ |
| Agent-led onboarding (checks deps, detects LLM backend, writes config) | ✅ |
| Scheduled ingest (cron/systemd timer) — same CLI, no watcher process | ✅ |
| Git change tracking of the document root (local history + optional private remote for web agents) | ✅ |
| Automatic chunking of oversized documents (character budget; no silent skip on large files) | ✅ |
| JSONL log of every LLM call (model, duration, retries, success) — local debug telemetry, not knowledge | ✅ |
| Layout-aware PDF extraction via marker (tables, forms) — external tool, opt out with `--no-marker` | ✅ Default on |
| Handwriting transcription + scene description for standalone images, via an optional vision-capable model (`--vision-model`) — no extra dependency, no face identification | ✅ Opt-in, falls back to tesseract-only OCR |
| Remote access for agents without local filesystem — **private git remote of aggregates** (Gitea/GitLab/…); MCP optional glue | ✅ Decision: git; see [Remote access via git](#remote-access-via-git) |
| Enrichment gate, derive/dream / cross-folder consolidation (extra reasoning on top of extraction) | ⏳ Optional/later — see [Roadmap](#roadmap) |

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full system design, scope amendments, and why each optional piece was cut or deferred.

## Prerequisites

| Tool | Purpose | Required for |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python package/venv management | Everything |
| An OpenAI-compatible LLM server | Structured extraction | [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`, LM Studio, or vLLM — local or LAN, your choice |
| [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) | Querying the knowledge base | Search |
| `tesseract` | Image OCR | `.png`/`.jpg`/`.jpeg` ingest |
| `ghostscript` (`gs`) | OCRmyPDF dependency | Scanned-PDF OCR |
| [marker](https://github.com/datalab-to/marker) (`marker_single`) | Layout-aware PDF extraction (tables, forms) | PDF ingest — on by default, opt out with `--no-marker` |

`marker` is **never bundled or listed in this repo's `pyproject.toml`**. Onboarding (or you)
installs it *externally* when the skill is set up — `pipx install marker-pdf` (or a sibling
venv) puts `marker_single` on PATH, same pattern as `tesseract`/`ghostscript`. The skill only
shells out to that binary. That keeps PyTorch weight and marker's GPL-3.0 / modified OpenRAIL-M
terms out of smart-okf's own MIT dependency graph (important if you publish the skill). Free for
personal/research use and startups under $2M revenue; commercial redistribution needs a license
from [datalab.to](https://www.datalab.to/pricing). Pass `--no-marker` / `use_marker: false` for
pdfplumber+OCRmyPDF only (no marker install).

First run? Just ask your agent to set it up — the [Onboarding](SKILL.md#onboarding-first-run) section of the skill walks through checking prerequisites, detecting a running LLM server, and choosing where your documents live.

## Installation

```bash
git clone https://github.com/TuxLux40/smart-okf.git
cd smart-okf
uv sync --group dev
```

To use it as a skill for Claude Code or another skill-aware agent, symlink the repo into the agent's skill directory:

```bash
ln -s "$(pwd)" ~/.claude/skills/smart-okf
```

## Quick start

### 1. Ingest a folder

```bash
uv run python scripts/ingest_folder.py /path/to/your/documents \
  --host http://127.0.0.1:1234 --model <your-model>
```

Each folder gets one aggregate Markdown file, named after the folder, covering every supported file directly inside it — subfolders get their own, separate aggregate:

```
documents/
├── documents.md      ← generated: aggregate of contract.pdf + notes.txt
├── contract.pdf
├── notes.txt
└── genealogy/
    ├── genealogy.md  ← generated: separate aggregate, just this folder's files
    └── birth.pdf
```

### 2. Re-run whenever documents change

```bash
uv run python scripts/ingest_folder.py /path/to/your/documents
```

Re-runs are incremental — unchanged files (tracked by SHA-256 in `source_hashes` frontmatter) are never re-sent to the LLM. Once `smart-okf.yaml` exists, drop the path entirely:

```bash
uv run python scripts/ingest_folder.py   # ingests every configured document_roots entry
```

Same command for cron:

```cron
0 3 * * 0  cd /path/to/smart-okf && uv run python scripts/ingest_folder.py
```

### 3. Ask questions through the skill

Once symlinked, just ask your agent — it searches the whole document tree (never just one topically-named folder, since real questions cut across folders) and answers from the aggregates, citing the source document.

## Change tracking

The document root is a plain git repository so agents (and you) can see what an ingest run
actually changed:

```bash
cd /path/to/your/documents
git init && git add -A && git commit -m "Initial snapshot"

# after a later ingest run:
git add -A && git commit -m "Ingest: $(date +%F)"
git diff HEAD~1 -- '*.md'      # see exactly what the last ingest changed
git log --stat                 # history of ingest runs over time
```

This is what makes re-ingest safe to run unattended: a synthesized summary that came out wrong,
or an in-place PDF OCR pass that misbehaved, is a `git revert` away instead of a silent,
unrecoverable overwrite. Locally you can track originals *and* generated `.md` aggregates in the
same repo — diffing both together is the point.

The same git history is also the **sync plane** for remote agents (next section). That is a
different job from the LLM call log (the section after that).

## Remote access via git

**Decision (R1): git is the remote access mechanism** — not a custom smart-okf API server, and
not “re-run extraction in the browser.”

Typical flow:

1. Ingest runs **on your machine** (local extractor + scripts) against the document tree.
2. Commit the resulting **aggregates** (and whatever else you choose to publish).
3. `git push` to a **private** remote you control — [Gitea](https://about.gitea.com/),
   [Forgejo](https://forgejo.org/), GitLab self-hosted, etc. Prefer private network / Tailscale
   over a public GitHub repo for sensitive personal docs.
4. Web agents (Claude, etc.) **consume Markdown**, not raw PDFs: clone/pull the private remote,
   or point a knowledge/project connector at that checkout.

**What to push.** Many setups push only `**/*.md` aggregates (and maybe a thin README) and keep
binaries/PDFs on the NAS only — smaller remote, less sensitive bulk, still enough for most
questions. Others push the full tree for true `git clone` backup. Choose explicitly; do not
assume “the whole documents folder must go to the remote.”

**Claude web and MCP.** A private Gitea/GitLab remote is a **git repo**, not an MCP server by
itself. Common patterns:

| Pattern | What it is |
|---------|------------|
| Clone/pull on a machine the agent can read | Simplest: skill or human updates a local clone; agent searches `.md` |
| Custom MCP that wraps a checkout | An MCP server (search/read tools) running against a clone of *your* private remote — MCP is glue, git remains source of truth |
| Host-native “add this repo / knowledge” | Depends on the product (Claude Projects, connectors, etc.); still usually ends up as Markdown-in, not OCR-in |

So: **yes — private git is the right sync mechanism for the `.md`s.** MCP is optional tooling on
top of a clone if a product wants tool-calling APIs; it is not a substitute for the remote, and
you do not need a smart-okf daemon for web agents to answer from already-ingested knowledge.

## LLM call log (JSONL) — not git

During evaluation of external tools (chonkie / langfuse / marker), **langfuse** was considered
for “what did each LLM call do?” Self-hosted langfuse wants Postgres + ClickHouse + Redis + S3 —
far heavier than a cron batch job justifies. Instead, ingest appends one JSON line per call
outcome to:

```text
<path-to-documents>/.okf-llm-log.jsonl
```

Each line roughly: timestamp, **model actually used**, host, prompt size, duration, retry count,
success/failure, error string. Grep it when something is flaky:

```bash
rg '"success": false' /path/to/documents/.okf-llm-log.jsonl
```

**Why not git for that?**

| | Git (document root) | JSONL LLM log |
|--|---------------------|---------------|
| **Job** | History of *knowledge files* (aggregates, maybe originals) | *Operational* telemetry of extractor calls |
| **Shape** | Meaningful snapshots humans/agents review | High-churn, append-only, one line per attempt |
| **Volume** | Commits after ingest runs | Can grow every retry, chunk, vision call |
| **Tracked?** | Yes — commit what you care about | Usually **gitignored** (noise, no useful diff) |

Git answers: “what did the last ingest change in `EON.md`?”  
JSONL answers: “why did that PDF burn three retries and 90 seconds on model X?”

They do not replace each other. (JSONL is also **not** from the chunking code — chunking only
splits long text before extraction; logging is a separate ~30-line append in `LLMClient`.)

## Configuration

`SmartOkfConfig` (`app/config.py`) loads settings in this order (lowest → highest precedence): field defaults → `smart-okf.yaml` (or `~/.config/smart-okf/smart-okf.yaml`) → environment variables (`SMART_OKF_` prefix). Copy [`smart-okf.example.yaml`](smart-okf.example.yaml) to `smart-okf.yaml`, or let the [onboarding flow](SKILL.md#onboarding-first-run) write it for you.

| Variable | Default | Description |
|---|---|---|
| `SMART_OKF_LLM_HOST` | `http://localhost:11434` | Any OpenAI-compatible `/v1/chat/completions` endpoint (must be localhost/RFC1918/allowlisted unless `allow_remote_llm`) |
| `SMART_OKF_LLM_MODEL` | `qwen2.5:3b` | Model name for extraction |
| `SMART_OKF_LLM_API_KEY` | `not-needed` | API key, only if your server requires one |
| `SMART_OKF_VISION_MODEL` | unset | Vision-capable model (served by `SMART_OKF_LLM_HOST`) for standalone image ingest — handwriting transcription + scene description. Unset: images fall back to tesseract-only OCR, no vision capability |
| `SMART_OKF_CONFIG` | `smart-okf.yaml` | Path to the YAML config file |

Supported document suffixes live in [`app/constants.py`](app/constants.py): `.pdf`, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx`, `.png`, `.jpg`, `.jpeg`.

## OKF output format

Each folder's aggregate is OKF markdown: YAML frontmatter, a synthesized orientation summary, then one body section per source document.

```yaml
---
type: FolderSummary
title: Contracts
description: Aggregated extraction of 2 document(s) in contracts/2024
tags: [legal, contract]
sources:
  - contracts/2024/lease.pdf
  - contracts/2024/isp.pdf
source_hashes:
  lease.pdf: 4a1f...
  isp.pdf: 9c02...
---

Two contracts on file: an apartment lease and an ISP agreement, both active as of 2024.

## Lease

_Source: lease.pdf_

...key terms and dates...

## Isp

_Source: isp.pdf_

...contract details...
```

Models and serialization: [`app/models/okf.py`](app/models/okf.py). Full format spec, reserved filenames, and type vocabulary: [`docs/OKF_SPEC.md`](docs/OKF_SPEC.md).

## Development

```bash
uv sync --group dev

# Lint, format, type-check, test
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q
```

CI runs the same checks on every push/PR to `main` ([`.github/workflows/python.yml`](.github/workflows/python.yml)).

### Project layout

```
app/
├── config.py               # SmartOkfConfig (YAML + env settings)
├── constants.py            # Shared defaults
├── exceptions.py           # LLMClientError, DocumentIngestError
├── models/okf.py           # OKFFrontmatter, OKFDocument
└── services/
    ├── ingest.py            # Per-folder aggregate ingest (non-recursive, hash-incremental)
    ├── llm_client.py         # OpenAI-compatible chat + extraction + summary synthesis
    ├── text_extraction.py    # PDF/docx/eml/csv/xlsx + marker/OCRmyPDF + tesseract
    ├── chunking.py           # Character-budget split for oversized docs
    ├── extraction_options.py # Extraction policy (marker on/off, …)
    └── prompts.py
SKILL.md                     # Agent skill entry point (onboarding, ingest, query)
prompts/                     # LLM system prompts
scripts/ingest_folder.py     # CLI: agent + cron entry point
docs/
├── DESIGN.md                 # System design, scope amendments, roadmap
└── OKF_SPEC.md                # OKF format spec + smart-okf conventions
tests/
```

Agent-oriented docs: [`AGENTS.md`](AGENTS.md), [`AGENT_GUIDES.md`](AGENT_GUIDES.md).

## Roadmap

Committed scope stays small on purpose: ingest → per-folder aggregate → ripgrep search, run by hand or on a schedule. Optional follow-ons in [`docs/DESIGN.md`](docs/DESIGN.md):

- **R1 — Remote agent access**: **decided — private git remote** of aggregates (Gitea/GitLab/…); MCP only as optional glue on a clone. See [Remote access via git](#remote-access-via-git). Remaining work is operational docs/examples, not an API server.
- **R2 — Cross-folder consolidation**: root-level concept files linking a matter that spans multiple folders' aggregates
- **R3 — Extraction verbosity valve**: tunable extraction detail (what's noise to one user is signal to another)
- **R4 — Semantic near-duplicate detection**: catches look-alike documents that hash comparison can't
- **R5 — Cron management commands**: install/list/remove the scheduled job, not just a documented crontab line
- **R6 — Docling as a swappable PDF/docx/xlsx/eml extraction backend**: MIT-licensed alternative to marker; unifies more formats behind one API and has native `.eml` support, but pulls in PyTorch same as marker and its native output isn't markdown — evaluated 2026-07-18, not adopted (see `docs/DESIGN.md`), worth a real look only if pdfplumber/OCRmyPDF quality becomes a specific pain point

Full historical design — including the since-cut folder watcher, per-file companions, and Ollama-only LLM client — plus the amendments explaining what changed and why: [`docs/DESIGN.md`](docs/DESIGN.md). Legacy notes: [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md).

## Core principles

- **Privacy & local-only** — raw extraction on your hardware; cloud orchestrators see finished Markdown, not PDFs, unless you deliberately open them.
- **Files stay yours** — originals never move into a proprietary DB; co-located aggregates + git are the backup/sync story.
- **Human + agent usable** — browse folders natively; local agents use the skill + ripgrep; remote agents use a private git remote of `.md`s.
- **OKF native** — portable, git-friendly, structured markdown with full provenance.
- **Bring your own LLM** — any OpenAI-compatible chat-completions server for *extraction*, no vendor lock-in.
- **Script = extractor engine; skill = how to drive it** — not “agent reinvents OCR every time.”

## Related

Inspired by understory (Codacus), Karpathy's LLM-wiki approach, and Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). Format details: [`docs/OKF_SPEC.md`](docs/OKF_SPEC.md).

## License

[MIT](LICENSE)
