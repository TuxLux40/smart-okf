# smart-okf

[![CI](https://github.com/TuxLux40/smart-okf/actions/workflows/python.yml/badge.svg)](https://github.com/TuxLux40/smart-okf/actions/workflows/python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![OKF v0.1](https://img.shields.io/badge/OKF-v0.1-informational.svg)](docs/OKF_SPEC.md)

**Local-first [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) knowledge base** for sensitive personal documents. Point it at a folder tree — health records, insurance, government correspondence, provider contracts — and it turns every folder into one aggregate Markdown file, extracted by an LLM you run yourself. Nothing leaves your machine, and the originals never move.

Ships as a [Claude Code / MCP-style agent skill](SKILL.md): install it once, and any skill-aware agent can ingest new documents and answer questions from the knowledge base on request — no server, no daemon, no webapp.

---

## Contents

- [Why not just use X?](#why-not-just-use-x)
- [How it works](#how-it-works)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [OKF output format](#okf-output-format)
- [Development](#development)
- [Roadmap](#roadmap)
- [Core principles](#core-principles)

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
2. Each supported file is read: PDF via `pdfplumber` (OCRed in place first if it's a scan), `.docx`/`.eml`/`.csv`/`.xlsx`/`.txt` natively, images via `tesseract`.
3. Your LLM extracts structured facts per file into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) markdown — any server speaking the OpenAI chat-completions API: Ollama, llama.cpp's `llama-server`, LM Studio, vLLM.
4. Every folder's extractions merge into **one aggregate `.md` in that folder** — non-recursive, a subfolder gets its own separate aggregate — with a synthesized orientation summary on top and full per-file provenance below.
5. Humans browse folders directly; agents query the aggregates via ripgrep, or invoke this skill.

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
| Git-based change tracking of the document root | ✅ |
| `index.md` generation, enrichment gate, derive/dream reasoning, FastAPI, MCP server | ⏳ Optional/later — see [Roadmap](#roadmap) |

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full system design, scope amendments, and why each optional piece was cut or deferred.

## Prerequisites

| Tool | Purpose | Required for |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python package/venv management | Everything |
| An OpenAI-compatible LLM server | Structured extraction | [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`, LM Studio, or vLLM — local or LAN, your choice |
| [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) | Querying the knowledge base | Search |
| `tesseract` | Image OCR | `.png`/`.jpg`/`.jpeg` ingest |
| `ghostscript` (`gs`) | OCRmyPDF dependency | Scanned-PDF OCR |

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

## Configuration

`SmartOkfConfig` (`app/config.py`) loads settings in this order (lowest → highest precedence): field defaults → `smart-okf.yaml` (or `~/.config/smart-okf/smart-okf.yaml`) → environment variables (`SMART_OKF_` prefix). Copy [`smart-okf.example.yaml`](smart-okf.example.yaml) to `smart-okf.yaml`, or let the [onboarding flow](SKILL.md#onboarding-first-run) write it for you.

| Variable | Default | Description |
|---|---|---|
| `SMART_OKF_LLM_HOST` | `http://localhost:11434` | Any OpenAI-compatible `/v1/chat/completions` endpoint (must be localhost/RFC1918/allowlisted unless `allow_remote_llm`) |
| `SMART_OKF_LLM_MODEL` | `qwen2.5:3b` | Model name for extraction |
| `SMART_OKF_LLM_API_KEY` | `not-needed` | API key, only if your server requires one |
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
    ├── text_extraction.py    # PDF/docx/eml/csv/xlsx + in-place OCRmyPDF + tesseract
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

Committed scope stays small on purpose: ingest → per-folder aggregate → ripgrep search, run by hand or on a schedule. Everything past that is optional/later, tracked as scoped-but-undecided proposals in [`docs/DESIGN.md`](docs/DESIGN.md):

- **R1 — Remote agent access**: self-hosted git remote vs. an MCP server (or both)
- **R2 — Cross-folder consolidation**: root-level concept files linking a matter that spans multiple folders' aggregates
- **R3 — Extraction verbosity valve**: tunable extraction detail (what's noise to one user is signal to another)
- **R4 — Semantic near-duplicate detection**: catches look-alike documents that hash comparison can't
- **R5 — Cron management commands**: install/list/remove the scheduled job, not just a documented crontab line

Full historical design — including the since-cut folder watcher, per-file companions, and Ollama-only LLM client — plus the amendments explaining what changed and why: [`docs/DESIGN.md`](docs/DESIGN.md). Legacy notes: [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md).

## Core principles

- **Privacy & local-only** — no cloud by default; processing runs on your own hardware.
- **Files stay yours** — originals never move, never get locked into a database; co-located aggregates mean `git clone` is the entire backup story.
- **Human + agent usable** — browse folders natively; agents traverse the same plain Markdown.
- **OKF native** — portable, git-friendly, structured markdown with full provenance.
- **Bring your own LLM** — any OpenAI-compatible chat-completions server, no vendor lock-in.

## Related

Inspired by understory (Codacus), Karpathy's LLM-wiki approach, and Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). Format details: [`docs/OKF_SPEC.md`](docs/OKF_SPEC.md).

## License

[MIT](LICENSE)
