# smart-okf

**Local-first OKF knowledge base** for sensitive documents — one aggregate Markdown file per folder, your own LLM for extraction, and an optional Honcho-inspired reasoning loop (store → derive → dream → query). Everything stays on your machine.

Turn folder hierarchies of PDFs, scans, and text files into structured, browsable, agent-parseable knowledge without sending data to the cloud.

## Why not just use X?

Mature alternatives exist and are worth considering first:

- **[Paperless-ngx](https://docs.paperless-ngx.com/)** — mature, self-hosted document management with OCR, full-text search, and a "Correspondents" concept (doctors, insurers, ISPs). Covers most of the "find my documents" need out of the box.
- **OpenWebUI RAG** — point a Knowledge collection straight at a folder of PDFs; zero custom pipeline.

Neither gives you **all three** of: local LLM-extracted structured facts, files that stay plain markdown next to the originals (not locked in a DB — `git clone` and `cat` are enough to read the whole thing), and a format any agent can traverse without a bespoke SDK or API call. That combination — human-browsable + agent-parseable + no server required to read it — is smart-okf's reason to exist. If you only need document search/retrieval and don't care about the co-located, git-portable, no-server-needed property, Paperless-ngx or OpenWebUI RAG will get you there faster.

## Features

| Capability | Status |
|------------|--------|
| One aggregate OKF `.md` per folder (`providers/` → `providers/providers.md`), non-recursive | ✅ |
| PDF, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx` ingest via any OpenAI-compatible LLM | ✅ |
| Pydantic OKF models with YAML frontmatter | ✅ |
| CLI folder ingest | ✅ |
| Scanned-PDF OCR, embedded in the PDF (OCRmyPDF, deu+eng) | ✅ |
| Standalone image OCR (`.png`, `.jpg`) | ❌ Not yet — skipped with clear message |
| Scheduled ingest (cron/systemd timer), hash-incremental re-runs | ✅ Same CLI, add a crontab line |
| `index.md`, enrichment gate, derive/dream reasoning, FastAPI, MCP | ❌ Optional/later — only if the simple loop below isn't enough |

See [`docs/DESIGN.md`](docs/DESIGN.md) (2026-07-17 scope amendment at the top) for the full system design, what's cut, and why.

## How It Works

```
Document folders (local storage)
        ↓ manual or cron-scheduled ingest
app/services/ingest.py  →  text_extraction  →  llm_client  →  one OKF .md per folder
        ↓ (optional/later)
enrichment, derive/dream, search, API, MCP
        ↓
Humans browse folders · agents via ripgrep / API (planned) / MCPJungle (planned)
```

1. Point smart-okf at a document folder (or run it on a schedule — cron, systemd timer).
2. Supported files are read (PDF via pdfplumber; `.docx`, `.eml`, `.csv`, `.xlsx`, `.txt` natively).
3. Your LLM extracts structured facts per file into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) markdown — any server speaking the OpenAI chat completions API: Ollama, llama.cpp's `llama-server`, vLLM, LM Studio, or a hosted OpenAI-compatible endpoint.
4. Every folder's extractions are merged into one aggregate `.md` **in that folder**, covering only the files directly inside it (a subfolder gets its own separate aggregate), with per-file provenance in frontmatter (`sources` field).
5. Humans browse folders directly; agents query via ripgrep, API, or MCP (planned).

## Prerequisites

- **Python** ≥ 3.11
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **An OpenAI-compatible LLM server** running locally or reachable on your network — [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`, vLLM, LM Studio, etc. Configure via `SMART_OKF_LLM_HOST` / `smart-okf.yaml` (default assumes Ollama on `localhost:11434`).
- **[ripgrep](https://github.com/BurntSushi/ripgrep)** (`rg`) — required for agent/CLI search over the knowledge base

```bash
# Example with Ollama:
ollama pull qwen2.5:3b
```

## Installation

```bash
git clone https://github.com/TuxLux40/smart-okf.git
cd smart-okf
uv sync --group dev
```

## Quick Start

### 1. Ingest a test folder

```bash
uv run python scripts/ingest_folder.py /path/to/your/documents
```

Each folder gets one aggregate OKF markdown file, named after the folder, covering every
supported file directly inside it (subfolders get their own, separate aggregate):

```
documents/
├── documents.md      ← generated: aggregate of contract.pdf + notes.txt
├── contract.pdf
├── notes.txt
└── genealogy/
    ├── genealogy.md   ← generated: separate aggregate, just this folder's files
    └── birth.pdf
```

### 2. Use as an agent skill

The repo root is a [SKILL.md](SKILL.md) skill package — symlink it into your agent's skill
directory (e.g. `~/.claude/skills/smart-okf`) and Claude Code (or any skill-aware agent) can
ingest and query the knowledge base on request. Cron uses the same CLI:

```
0 3 * * 0  cd /path/to/smart-okf && uv run python scripts/ingest_folder.py /path/to/documents --host http://127.0.0.1:1234 --model <model>
```

Re-runs are incremental: aggregates carry SHA-256 hashes per source (`source_hashes`
frontmatter), unchanged files are never re-sent to the LLM. Scanned PDFs get their OCR text
layer embedded in place (OCRmyPDF, deu+eng) — OCR runs once per document, ever, and the text
stays usable in PDF editors.

## Configuration

`SmartOkfConfig` (`app/config.py`) loads settings in this order (lowest to highest precedence):
defaults → `smart-okf.yaml` (or `~/.config/smart-okf/smart-okf.yaml`) → environment variables
(`SMART_OKF_` prefix). Copy [`smart-okf.example.yaml`](smart-okf.example.yaml) to `smart-okf.yaml`
and set at least one `document_roots` entry (required).

| Variable | Default | Description |
|----------|---------|-------------|
| `SMART_OKF_LLM_HOST` | `http://localhost:11434` | Any OpenAI-compatible `/v1/chat/completions` endpoint (must be localhost/RFC1918/allowlisted unless `allow_remote_llm`) |
| `SMART_OKF_LLM_MODEL` | `qwen2.5:3b` | Model name for extraction |
| `SMART_OKF_LLM_API_KEY` | `not-needed` | API key, if your server requires one (local servers usually don't) |
| `SMART_OKF_CONFIG` | `smart-okf.yaml` | Path to the YAML config file |

Constants live in [`app/constants.py`](app/constants.py). Supported document suffixes: `.pdf`, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx` (`.png`/`.jpg`/`.jpeg` accepted but fail fast — OCR not yet processed).

## OKF Output Format

Each folder's aggregate file is OKF markdown — YAML frontmatter plus one body section per source
document:

```yaml
---
type: FolderSummary
title: Contracts
description: Aggregated extraction of 2 document(s) in contracts/2024
tags: [legal, contract]
sources:
  - contracts/2024/lease.pdf
  - contracts/2024/isp.pdf
---

## Lease

_Source: lease.pdf_

...key terms and dates...

## Isp

_Source: isp.pdf_

...contract details...
```

Models and serialization: [`app/models/okf.py`](app/models/okf.py).

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Lint, format, type-check, test
uv run ruff check --fix . && uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q
```

CI runs the same checks on push/PR to `main` (see [`.github/workflows/python.yml`](.github/workflows/python.yml)).

### Project layout

```
app/
├── constants.py          # Shared defaults
├── exceptions.py         # LLMClientError, DocumentIngestError
├── models/okf.py         # OKFFrontmatter, OKFDocument
├── services/
│   ├── ingest.py         # Per-folder aggregate ingest (non-recursive, hash-incremental)
│   ├── llm_client.py     # OpenAI-compatible chat + extraction
│   ├── text_extraction.py  # PDF/docx/eml/xlsx + in-place OCRmyPDF
│   └── prompts.py
SKILL.md                  # Agent skill entry point
prompts/                  # LLM system prompts
scripts/ingest_folder.py  # CLI wrapper
docs/DESIGN.md            # System design + PR plan
tests/
```

Agent-oriented docs: [`AGENTS.md`](AGENTS.md), [`AGENT_GUIDES.md`](AGENT_GUIDES.md).

## Roadmap

Committed scope is intentionally small: models, per-folder aggregate ingest, LLM client, CLI, a
cron-friendly ingest command. Everything past that — OCR for images, `index.md` generation,
enrichment gate, derive/dream reasoning, FastAPI, MCP tools — is optional/later, built only if the
simple ingest → aggregate → ripgrep-search loop turns out not to be enough.

Full historical design (including the since-cut watcher/per-file-companion/Ollama-only design) and
the amendment explaining what changed: [`docs/DESIGN.md`](docs/DESIGN.md) · legacy notes:
[`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md)

## Core Principles

- **Privacy & local-only** — no cloud by default; processing on your hardware (Proxmox, NAS, laptop).
- **Human + agent usable** — browse folders natively; agents follow links, indices, and frontmatter.
- **OKF native** — portable, git-friendly, structured markdown with provenance.
- **Your LLM backend** — any OpenAI-compatible chat completions server: Ollama, llama.cpp, vLLM, LM Studio.
- **Honcho-inspired loop (optional/later)** — ingest events → background reasoning → persistent insights in the folder aggregates.

## Related

Inspired by understory (Codacus), Karpathy's LLM-wiki approach, and Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). Honcho loop concept adapted for local LLM + document KB. Format details: [`docs/OKF_SPEC.md`](docs/OKF_SPEC.md).

Homelab integrations planned: MCPJungle, OpenWebUI, Tailscale LAN access.

## License

MIT