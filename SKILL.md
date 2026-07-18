---
name: smart-okf
description: Ingest and query a local-first OKF knowledge base of personal documents (health, insurance, government, providers/ISP, finances, contracts). Turns folders of PDFs, docx, eml, csv, xlsx, and txt files into one aggregate OKF markdown file per folder using a local OpenAI-compatible LLM, then answers questions from those aggregates. Use this skill whenever the user asks to ingest/OCR/index their documents, update or rebuild their document knowledge base, or asks a question answerable from their personal documents — "what does my ISP contract say", "when was my last doctor visit", "find my insurance policy number" — even if they don't mention OKF or smart-okf by name.
---
# smart-okf — personal document knowledge base

Local-first OKF (Open Knowledge Format) knowledge base. Each document folder gets **one
aggregate markdown file** (`<folder>/<folder-name>.md`) summarizing every supported file directly
inside it — non-recursive, subfolders get their own aggregate. Everything runs locally; documents
never leave the machine.

Three operations: **onboarding** (first run only), **ingest** (build/refresh aggregates), and
**query** (answer from aggregates).

## Onboarding (first run)

If no `smart-okf.yaml` exists in the skill root (`ls smart-okf.yaml`) and the user hasn't
already told you where their documents live and which LLM to use, run this interview before
doing anything else. This is a conversation you conduct, not a script to invoke — walk the user
through it, don't dump all the questions at once.

1. **Check system prerequisites** — run each and note what's missing, don't just assume:

   ```bash
   command -v rg && command -v tesseract && command -v gs
   ```

   `rg` (ripgrep) is needed for querying; `tesseract` for image OCR; `gs` (Ghostscript) is an
   OCRmyPDF dependency for scanned-PDF OCR. For anything missing, detect the package manager
   (`command -v pacman`/`apt`/`dnf`/`brew`) and give the user the exact install command —
   **ask before running a package-manager install yourself**, since it needs sudo and touches
   the system outside this project.

2. **Detect a local LLM backend** — probe the common defaults before asking the user to type
   a host:

   ```bash
   for url in http://localhost:11434 http://127.0.0.1:1234 http://localhost:8080; do
     curl -s -m 2 "$url/v1/models" && echo " <- $url"
   done
   ```

   Ollama defaults to `:11434`, LM Studio to `:1234`, llama.cpp's `llama-server` commonly to
   `:8080`. If one responds, list its models and ask the user which to use for extraction. If
   none respond, ask what they use and where it runs.

3. **Ask where their documents live** (`document_roots` — can be more than one path) and
   confirm the folder actually exists and looks like personal documents, not a code repo or
   media library, before proceeding.

4. **Write `smart-okf.yaml`** in the skill root from what you learned (see
   [smart-okf.example.yaml](smart-okf.example.yaml) for the shape: `document_roots`,
   `llm_host`, `llm_model`). This is a plain YAML file — write it directly, you don't need a
   script for this.

5. Offer to run a first ingest on one subfolder as a smoke test before ingesting everything —
   see **Ingest cautions** below for why.

## Query (default operation)

Answer questions from existing aggregates — no LLM server needed, they're plain markdown.

**Always search the entire documents root, never just the topically-named folder.** Example: Real-life
processes cut across the folder taxonomy: a government benefits application needs data from
`finances/` AND `insurances/` AND `providers/` AND `apartments/`; a dispute with a utility
provider spans `providers/`, `finances/`, and `lawyers/`. Answering "help with finances" from
`finances/` alone silently misses reference numbers, dates, and amounts that
live elsewhere — the single most common failure mode this KB exists to prevent.

1. Find candidate aggregates with ripgrep **from the root**. Aggregates are named after their
   folder and carry `type: FolderSummary` frontmatter:

   ```bash
   rg -l --glob '*.md' 'type: FolderSummary' /path/to/documents      # list all aggregates
   rg -i -C3 'vodafone|kündigungsfrist' /path/to/documents --glob '*.md'   # content search, whole tree
   ```
2. Read the matching aggregate(s). Each has YAML frontmatter (`sources:` lists the original
   files), an orientation summary at the top for folders with 2+ documents (a few sentences,
   sometimes a mermaid timeline of key dates), then one `## <Title>` body section per source
   document with `_Source: <filename>_` provenance lines.
3. When an aggregate's summary is too thin for the question (a specific amount, a full
   reference number, exact wording), read the **raw transcript** instead of re-extracting:
   `<root>/.okf-transcripts/<relative-path>.txt` holds the complete extracted text of every
   ingested file. Search it directly: `rg -i 'aktenzeichen' /path/to/documents/.okf-transcripts/`.
4. Answer, citing the source document filename(s) from the provenance lines — not just the
   aggregate. If the aggregate looks stale or thin (the folder has more source files than
   `sources:` lists), say so and offer to re-ingest that folder.

If no aggregate exists for the relevant folder yet, offer to ingest it first.

## Change tracking

The documents root is a git repository — commit after each ingest run so agents can diff what
changed (`git -C /path/to/documents log --stat`, `git diff HEAD~1 -- '*.md'`). Use it to answer
"what's new since last month" questions and to safely revert a bad aggregate or OCR pass.

## Ingest

Requires an OpenAI-compatible LLM server (LM Studio, llama.cpp `llama-server`, Ollama, vLLM).
Check reachability before starting: `curl -s $SMART_OKF_LLM_HOST/v1/models`.

```bash
cd /home/oliver/Projects/smart-okf   # skill root — scripts import the app/ package
SMART_OKF_LLM_HOST=http://127.0.0.1:1234 \
SMART_OKF_LLM_MODEL=gemma-4-e4b-it-qat \
uv run python scripts/ingest_folder.py /path/to/documents
```

- Supported: `.pdf`, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx`, and images (`.png`/`.jpg`/`.jpeg`
  via tesseract OCR, read-only).
- **Scanned PDFs are OCRed in place**: OCRmyPDF (deu+eng) embeds a text layer into the
  original PDF when it has none, so OCR runs once per document ever — later ingests and PDF
  editors reuse the embedded layer. This rewrites the PDF file itself (content preserved).
  Standalone images are never modified — their OCR text lives in the transcript store and
  aggregate only.
- **Every extraction writes a raw transcript** to `<root>/.okf-transcripts/<relpath>.txt` —
  the lossless full text, so OCR/extraction never needs to repeat and agents can read exact
  wording without touching originals.
- **Ingest is incremental**: each aggregate stores SHA-256 hashes of its sources in
  frontmatter (`source_hashes`). Re-runs skip unchanged files entirely — no LLM calls, no
  rewrites — so scheduled re-ingests of a mostly-static tree are cheap. Only changed, new, or
  removed files trigger work in their folder.
- Roughly one LLM call per changed source file, so a large first run takes time. Ingest one
  subfolder at a time on first runs and check output quality before continuing. Documents too
  large for a single call (over ~8000 characters of extracted text) are chunked automatically
  and merged back into one aggregate section — this is transparent, no flag needed.
- Every LLM call (chunked or not) is logged to `<root>/.okf-llm-log.jsonl` — model, duration,
  retry count, success/failure. Useful for spotting a flaky backend or unusually slow document:
  `rg '"success": false' /path/to/documents/.okf-llm-log.jsonl`.
- Pass `--use-marker` for layout-aware PDF extraction (tables, forms) if the user has
  [marker](https://github.com/datalab-to/marker)'s `marker_single` installed — see
  Prerequisites in [README.md](README.md). Off by default; explicit-fails (not silent
  fallback) if requested but not installed.
- The run reports written aggregates, unchanged folders, and skipped files at the end; relay
  written + skipped to the user.
- Cron/systemd-timer use the same command — no daemon, no watcher. Example crontab line:

  ```
  0 3 * * 0  cd /home/oliver/Projects/smart-okf && SMART_OKF_LLM_HOST=http://127.0.0.1:1234 SMART_OKF_LLM_MODEL=gemma-4-e4b-it-qat uv run python scripts/ingest_folder.py /home/oliver/nas/home/documents
  ```

### Ingest cautions

- Never ingest folders containing unrelated project files (web assets, git repos, media). Check
  what's in a folder before pointing ingest at a whole tree; suggest excluding junk folders.
- Aggregates are overwritten when their folder's files change — by design (rebuild from
  filesystem truth), but warn the user if they hand-edited an aggregate: manual edits survive
  only as long as no source file in that folder changes.
- In-place PDF OCR rewrites original documents. Content is preserved (OCRmyPDF only adds the
  text layer), but if the user is cautious about file mutation, mention it before the first
  ingest of a folder with scanned PDFs.
- `index.md` and `log.md` are reserved OKF filenames; a folder literally named `index` or `log`
  is skipped rather than overwriting them.

## OpenWebUI integration

If pointing an OpenWebUI Knowledge collection at this folder tree: **sync only the `.md`
aggregates, never the raw document folder.** OpenWebUI's folder sync has no filter — it will
also pick up PDFs, images, and stray temp files it can't parse and may hang on (observed:
hung on a `.jpg` in a `temp/`-style folder). Point the sync at a filtered view instead:

```bash
find /path/to/documents -name '*.md' -not -path '*/.okf-transcripts/*'
```

or symlink/copy just the `.md` files into a separate folder OpenWebUI syncs from, keeping the
real tree (originals + aggregates) untouched.

## Conventions (short form)

- Frontmatter: `type` required (`FolderSummary` for aggregates); `sources:` lists original file
  paths relative to the ingest root — this is the provenance chain, preserve it in any edit.
- Cross-links between concepts are plain markdown links; broken links are tolerated, not errors.
- Full format rules, type vocabulary, and spec references: read [docs/OKF_SPEC.md](docs/OKF_SPEC.md)
  when authoring or editing OKF files by hand.

## Configuration

Environment variables (or `smart-okf.yaml`, see [smart-okf.example.yaml](smart-okf.example.yaml)):

| Variable                  | Default                    | Purpose                                          |
| ------------------------- | -------------------------- | ------------------------------------------------ |
| `SMART_OKF_LLM_HOST`    | `http://localhost:11434` | OpenAI-compatible`/v1/chat/completions` server |
| `SMART_OKF_LLM_MODEL`   | `qwen2.5:3b`             | Model name as the server reports it              |
| `SMART_OKF_LLM_API_KEY` | `not-needed`             | Only for servers that require auth               |

Remote (non-localhost/RFC1918) LLM hosts are refused unless `allow_remote_llm` is set — keeps
sensitive documents off the cloud by default.
