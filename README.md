# smart-okf

**Smart OKF** — A local-first, privacy-preserving knowledge base system for your sensitive documents.

Co-located OKF-structured Markdown files live alongside your original documents (PDFs, scans, etc.). A lightweight web app orchestrates OCR, structured extraction via your own local LLM, enrichment, and Honcho-inspired reasoning loops (store → derive → dream/reason → query). Everything stays on your machine (Proxmox / NAS / local storage). Integrates cleanly with OpenWebUI, MCPJungle, and your existing homelab agents.

## Core Principles
- **Privacy & Local-only**: No cloud. All processing and storage on your hardware.
- **Human + Agent Usable**: Browse folders and read rich MD summaries/indices without opening originals. Agents follow breadcrumbs, links, and indices.
- **OKF Native**: Uses Google's Open Knowledge Format (markdown + YAML frontmatter) for portable, git-friendly, agent-parseable knowledge.
- **Your LLM Backend**: Full control — configure any local model (Ollama, llama.cpp, etc.). Small dedicated model recommended for extraction/reasoning.
- **Honcho-Inspired Loop** (adapted, local LLM only): Ingest events → Background reasoning (explicit facts + deductive + inductive patterns + conflict detection + link suggestions + actions) → Persistent insights back into co-located MDs.
- **Low Friction**: Web UI for management + review. Co-located files for instant human access.

## Quick Start (Scaffolding)
1. Clone or copy this repo.
2. `uv sync` (or pip install -e .) — see pyproject.toml.
3. Configure your local LLM endpoint in `app/config.py` or env.
4. Run the web app (Streamlit or FastAPI).
5. Point at a test document folder → ingest → watch MDs appear alongside originals.
6. Trigger reasoning pass.
7. Browse folders or query via API/MCP.

See `DEVELOPMENT_PLAN.md` for phased roadmap.

## Tech Stack (Initial)
- Python (uv) + FastAPI or Streamlit for web app
- Local LLM: Ollama / llama.cpp (configurable)
- OCR: pdfplumber / marker + easyocr / tesseract (LLM refinement)
- OKF handling: Pydantic models + markdown + YAML
- Watcher: watchdog
- Optional: MCP server tools for agent integration

## Project Status
Scaffolding stage. Core structure, models, basic prompts, and plan in place. See DEVELOPMENT_PLAN.md.

## License
MIT or your preference. Private/personal use primary.

## Related
- Inspired by understory (Codacus), Karpathy LLM-wiki, Google OKF spec.
- Honcho loop concept adapted for local LLM + OKF document KB.
- Your homelab: Proxmox, MCPJungle, OpenWebUI, local models.

Contributions / feedback welcome via issues or PRs (or direct to me).
