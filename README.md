# smart-okf

**Local-first OKF knowledge base** for sensitive documents — co-located Markdown companions, your own LLM for extraction, and Honcho-inspired reasoning (store → derive → dream → query). Everything stays on your machine.

Turn folder hierarchies of PDFs, scans, and text files into structured, browsable, agent-parseable knowledge without sending data to the cloud.

## Why not just use X?

Mature alternatives exist and are worth considering first:

- **[Paperless-ngx](https://docs.paperless-ngx.com/)** — mature, self-hosted document management with OCR, full-text search, and a "Correspondents" concept (doctors, insurers, ISPs). Covers most of the "find my documents" need out of the box.
- **OpenWebUI RAG** — point a Knowledge collection straight at a folder of PDFs; zero custom pipeline.

Neither gives you **all three** of: local LLM-extracted structured facts, files that stay plain markdown next to the originals (not locked in a DB — `git clone` and `cat` are enough to read the whole thing), and a format any agent can traverse without a bespoke SDK or API call. That combination — human-browsable + agent-parseable + no server required to read it — is smart-okf's reason to exist. If you only need document search/retrieval and don't care about the co-located, git-portable, no-server-needed property, Paperless-ngx or OpenWebUI RAG will get you there faster.

## Features

| Capability | Status |
|------------|--------|
| Co-located OKF `.md` companions (`file.pdf` → `file.md`) | ✅ |
| PDF, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx` ingest via any OpenAI-compatible LLM | ✅ |
| Pydantic OKF models with YAML frontmatter | ✅ |
| CLI folder ingest | ✅ |
| Streamlit UI skeleton | ⚠️ Placeholder |
| Image OCR (`.png`, `.jpg`) | ❌ Not yet — fails fast until OCR lands |
| Folder watcher, `index.md`, enrichment gate | ❌ Planned, optional |
| Derive / Dream reasoning loop | ❌ Prompts exist, not wired, optional |
| FastAPI REST + MCP tools | ❌ Planned, optional |

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
2. Supported files are read (PDF via pdfplumber; `.docx`, `.eml`, `.csv`, `.xlsx`, `.txt` natively).
3. Your LLM extracts structured facts into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) markdown — any server speaking the OpenAI chat completions API: Ollama, llama.cpp's `llama-server`, vLLM, LM Studio, or a hosted OpenAI-compatible endpoint.
4. Companion `.md` files are written next to the originals with provenance in frontmatter (`source` field).
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

Configure the LLM host and model in the sidebar, then trigger ingest from the **Ingest** tab.

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

Each companion file is OKF markdown — YAML frontmatter plus a structured body:

```yaml
---
type: DocumentSummary
title: Contract Review
description: Summary of key terms and dates
tags: [legal, contract]
source: contracts/2024/contract.pdf
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
│   ├── llm_client.py     # OpenAI-compatible chat + extraction
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
- **Your LLM backend** — any OpenAI-compatible chat completions server: Ollama, llama.cpp, vLLM, LM Studio.
- **Honcho-inspired loop** — ingest events → background reasoning → persistent insights in co-located MDs.

## Related

Inspired by understory (Codacus), Karpathy's LLM-wiki approach, and Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). Honcho loop concept adapted for local LLM + document KB. Format details: [`docs/OKF_SPEC.md`](docs/OKF_SPEC.md).

Homelab integrations planned: MCPJungle, OpenWebUI, Tailscale LAN access.

## License

MIT