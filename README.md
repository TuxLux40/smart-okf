# smart-okf

**Local-first OKF knowledge base** for sensitive documents — co-located Markdown companions, local LLM extraction, and Honcho-inspired reasoning (store → derive → dream → query). Everything stays on your machine.

Turn folder hierarchies of PDFs, scans, and text files into structured, browsable, agent-parseable knowledge without sending data to the cloud.

## Features

| Capability | Status |
|------------|--------|
| Co-located OKF `.md` companions (`file.pdf` → `file.md`) | ✅ |
| PDF + plain-text ingest via local Ollama | ✅ |
| Pydantic OKF models with YAML frontmatter | ✅ |
| CLI folder ingest | ✅ |
| Streamlit UI skeleton | ⚠️ Placeholder |
| Image OCR (`.png`, `.jpg`) | ❌ Not yet — fails until PR 3a |
| Folder watcher, `index.md`, enrichment gate | ❌ Planned |
| Derive / Dream reasoning loop | ❌ Prompts exist, not wired |
| FastAPI REST + MCP tools | ❌ Planned |

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full system design and phased PR plan.

## How It Works

```
Document folders (local storage)
        ↓ watcher / manual ingest
app/services/ingest.py  →  text_extraction  →  llm_client  →  OKF .md
        ↓ (planned)
KB manager, enrichment, derive/dream, search, API, MCP
        ↓
Humans browse folders · agents via ripgrep / API / MCPJungle
```

1. Point smart-okf at a document folder.
2. Supported files are read (PDF via pdfplumber, `.txt` as UTF-8).
3. A local LLM (Ollama) extracts structured facts into [OKF](https://github.com/google/okf) markdown.
4. Companion `.md` files are written next to the originals with provenance in frontmatter (`source` field).
5. Humans browse folders directly; agents query via ripgrep, API, or MCP (planned).

## Prerequisites

- **Python** ≥ 3.11
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **[Ollama](https://ollama.com/)** running locally with a small model (default: `qwen2.5:3b`)
- **[ripgrep](https://github.com/BurntSushi/ripgrep)** (`rg`) — required for agent/CLI search over the knowledge base

```bash
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

For each supported file, a co-located OKF markdown companion appears alongside the original:

```
documents/
├── contract.pdf
├── contract.md      ← generated
├── notes.txt
└── notes.md         ← generated
```

### 2. Streamlit UI (skeleton)

```bash
uv run streamlit run app/ui/streamlit_app.py
```

Configure the Ollama host and model in the sidebar, then trigger ingest from the **Ingest** tab.

## Configuration

Configuration is via environment variables today (`app/config.py` is planned):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `DEFAULT_MODEL` | `qwen2.5:3b` | Model name for extraction |

Constants live in [`app/constants.py`](app/constants.py). Supported document suffixes: `.pdf`, `.txt`, `.png`, `.jpg`, `.jpeg` (images not yet processed).

## OKF Output Format

Each companion file is OKF markdown — YAML frontmatter plus a structured body:

```yaml
---
type: DocumentSummary
title: Contract Review
description: Summary of key terms and dates
tags: [legal, contract]
source: contracts/2024/contract.pdf
okf_version: "0.1"
---

## Key Facts
...
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
│   ├── ingest.py         # Folder + file ingest
│   ├── llm_client.py     # Ollama chat + extraction
│   ├── text_extraction.py
│   └── prompts.py
└── ui/streamlit_app.py   # Skeleton UI
prompts/                  # LLM system prompts
scripts/ingest_folder.py  # CLI wrapper
docs/DESIGN.md            # System design + PR plan
tests/
```

Agent-oriented docs: [`AGENTS.md`](AGENTS.md), [`AGENT_GUIDES.md`](AGENT_GUIDES.md).

## Roadmap

| Phase | Focus |
|-------|-------|
| **0** (current) | Scaffolding — models, ingest, LLM client, CLI |
| **1** | Watcher, OCR for images, KB manager, `index.md`, derive loop |
| **2** | Full Streamlit UI, review queue, FastAPI |
| **3** | MCP tools (MCPJungle), OpenWebUI integration |
| **4** | Graph viz, git auto-commit, advanced search |

Details: [`docs/DESIGN.md`](docs/DESIGN.md) · legacy notes: [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md)

## Core Principles

- **Privacy & local-only** — no cloud by default; processing on your hardware (Proxmox, NAS, laptop).
- **Human + agent usable** — browse folders natively; agents follow links, indices, and frontmatter.
- **OKF native** — portable, git-friendly, structured markdown with provenance.
- **Your LLM backend** — Ollama today; llama.cpp and others planned.
- **Honcho-inspired loop** — ingest events → background reasoning → persistent insights in co-located MDs.

## Related

Inspired by understory (Codacus), Karpathy's LLM-wiki approach, and Google's [Open Knowledge Format](https://github.com/google/okf). Honcho loop concept adapted for local LLM + document KB.

Homelab integrations planned: MCPJungle, OpenWebUI, Tailscale LAN access.

## License

MIT