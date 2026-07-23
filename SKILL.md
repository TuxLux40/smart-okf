---
name: smart-okf
description: Ingest and query a local-first OKF knowledge base of personal documents (health, insurance, government, providers/ISP, finances, contracts). Turns folders of PDFs, docx, eml, csv, xlsx, and txt files into one aggregate OKF markdown file per folder using a local OpenAI-compatible LLM, then answers questions from those aggregates. Use this skill whenever the user asks to ingest/OCR/index their documents, update or rebuild their document knowledge base, or asks a question answerable from their personal documents — "what does my ISP contract say", "when was my last doctor visit", "find my insurance policy number" — even if they don't mention OKF or smart-okf by name.
---
# smart-okf — personal document knowledge base

OKF (Open Knowledge Format) knowledge base for personal document folders. Each folder gets **one
aggregate markdown file** (`<folder>/<folder-name>.md`) for every supported file directly inside
it — non-recursive; subfolders get their own aggregate.

**Core purpose:**

- **Aggregates = library of atomic facts** (IDs, date ranges, amounts, provenance)
- **Synthesis (roadmap) = librarian** — same story across folders, conflicts, patterns, next steps
- **Retrieval ladder (below) = how agents must use that library** — not one topical folder and hope

Honcho-as-architecture is out; Honcho-as-inspiration for smarter passes over MDs is in. Extract
runs via the ingest script (local or hosted model); query prefers MDs + transcripts + git.

Three operations: **onboarding** (first run only), **ingest** (build/refresh the library), and
**query** (retrieve from the library — and later, synthesized matter files).

## Onboarding (first run)

If no `smart-okf.yaml` exists in the skill root (`ls smart-okf.yaml`) and the user hasn't
already told you where their documents live and which LLM to use, run this interview before
doing anything else. This is a conversation you conduct, not a script to invoke — walk the user
through it, don't dump all the questions at once.

**Two roles (say this once early — it answers "why a local model if Claude is driving?"):**

- **Orchestrator** = you (Claude Code / OpenWebUI / Hermes / cron): decide when to ingest and
  answer from finished `.md` files. You never send raw PDF/image bytes to a cloud model for
  extraction.
- **Extractor** = the local OpenAI-compatible model the *script* always calls
  (`llm_host` / `llm_model`). Cron and interactive agent runs behave the same because
  extraction is always that second call inside `scripts/ingest_folder.py`.

There is no "skip the script; orchestrator extracts every PDF by hand every time" mode — the
script has no callback into the live agent, and cron needs the same engine. Orchestrator and
extractor can be different models. **Privacy is a degree:** default is local/LAN extractor so
raw OCR need not enter a cloud chat; with `allow_remote_llm` you may use a hosted extractor.
At **query** time, prefer aggregates + transcripts + git even if the orchestrator is hosted —
do not re-read every original PDF for facts that were already distilled.

1. **Where tools install** — system CLIs (`rg`, `tesseract`, `gs`, `marker_single`) and the
   Python skill venv (`uv sync`) live on the **machine that runs ingest and hosts the
   extractor model**, not necessarily on a NAS that only holds the document tree. Documents
   may be remote-mounted (SSHFS/NFS); deps and GPU/CPU inference stay on the workstation.

2. **Check system prerequisites** — run each and note what's missing, don't just assume:

   ```bash
   command -v rg && command -v tesseract && command -v gs && command -v marker_single
   ```

   `rg` (ripgrep) is needed for querying; `tesseract` for image OCR; `gs` (Ghostscript) is an
   OCRmyPDF dependency for scanned-PDF OCR when `--no-marker` is used; `marker_single` is the
   default layout-aware PDF backend (tables, forms). **marker is not bundled in this repo** —
   install it *externally* the same way as tesseract: `pipx install marker-pdf` (own venv, own
   PyTorch). Its code is GPL-3.0 and model weights use a modified OpenRAIL-M license (free for
   personal/research use; commercial redistribution needs a license from datalab.to).
   `--no-marker` / `use_marker: false` skips it and uses pdfplumber+OCRmyPDF only. For
   `rg`/`tesseract`/`gs`, detect the package manager (`command -v pacman`/`apt`/`dnf`/`brew`)
   and give the exact install command. **Ask before running any install yourself.**

3. **Detect a local LLM backend** (the extractor) — probe common defaults before asking:

   ```bash
   for url in http://localhost:11434 http://127.0.0.1:1234 http://localhost:8080; do
     curl -s -m 2 "$url/v1/models" && echo " <- $url"
   done
   ```

   Ollama defaults to `:11434`, LM Studio to `:1234`, llama.cpp's `llama-server` commonly to
   `:8080`. If one responds, list its models and ask which to use for **extraction** —
   prefer a 7B+ instruction-tuned model over a 2–3B one if hardware fits; extraction quality
   (OKF structure, not missing fields) scales with model size. If none respond, ask what they
   use and where it runs. Remind them this model is the *extractor*, not the chat agent
   driving the skill.

   If the user has standalone images (photos, meter readings, scans without a PDF wrapper),
   also ask whether a listed model is vision-capable (`vl`/`vision` in the name) for
   handwriting + brief scene description (never identifies people). Optional. Written to
   `vision_model` in `smart-okf.yaml` if yes. Vision + structured extraction = two LLM calls
   per image.

4. **Ask which model should dream** (`dream_model` / `dream_host`). The dream pass
   (see **Dreaming** below) is cross-folder *reasoning* — conflicts, patterns, matter
   linking — and benefits from the smartest model available more than any other stage;
   the extractor's small fast model is often not the right choice here. Offer three
   options and explain the tradeoff:

   - **Same as extractor** (default — leave `dream_model` unset): fine to start, weakest
     reasoning.
   - **Bigger local model**: same or another local host (a second machine's llama.cpp,
     a GPU box on the LAN). Best quality without data leaving the network. If their
     backend lists larger models (30B+, `thinking`/`reasoner` variants), suggest one.
   - **Hosted model** (`dream_host` pointing at a cloud API + `allow_remote_llm: true`):
     strongest reasoning. Be explicit about what leaves the machine: not the raw
     documents, but the aggregate *digests* — distilled personal facts, names, reference
     numbers. Only with informed consent, never as a silent default.

   Dreaming runs rarely (after ingest batches), so a slow-but-smart model costs little.

5. **Ask where their documents live** (`document_roots` — can be more than one path) and
   confirm the folder exists and looks like personal documents, not a code repo or media
   library.

6. **Write `smart-okf.yaml`** in the skill root from what you learned (see
   [smart-okf.example.yaml](smart-okf.example.yaml): `document_roots`, `llm_host`, `llm_model`,
   optional `vision_model` / `dream_model` / `dream_host` / `use_marker`). Plain YAML —
   write it directly; there is no `scripts/onboard.py`.

7. Offer a first ingest on one subfolder as a smoke test before the whole tree — see
   **Ingest cautions** below.

## Query (default operation)

Answer from existing knowledge — no extractor LLM needed for Q&A. Retrieval is **not** a
vector DB: it is **whole-tree ripgrep + read + git**, with an explicit fallback ladder.
**You must follow this ladder**; do not only open the topically named folder.

### Retrieval ladder (do this every time)

| Step | Where | Use for |
|------|--------|---------|
| 0 | **Synthesis** (`<root>/synthesis.md`, `type: Synthesis`) | Cross-folder matters, conflicts, patterns, open actions — check first for any question that could span folders; it names the aggregates to read next |
| 0.5 | **Matter files** (`<root>/matters/*.md`, `type: Matter`) | A specific cross-folder case already resolved to a dedicated file — check here when the synthesis or a shared ID points at one before reading every cited aggregate |
| 1 | **Aggregates** (`**/*.md` with `type: FolderSummary`) | Distilled facts, tags, orientation summary, provenance — **always start here** for folder-level facts |
| 2 | **Transcripts (mandatory fallback)** (`.okf-transcripts/`) | When MD is thin, partial, or missing a full ID/amount/quote — search here **before** re-ingest or guessing. Hidden folder; greppable; lossless raw extract |
| 3 | **Git history** | “What’s new,” same-batch uploads, ID-tagged commits months later |
| 4 | **JSONL** (`.okf-llm-log.jsonl`) | Ingest debugging only — **not** knowledge retrieval |

Steps 0 and 0.5 exist only after a dream pass has run (see **Dreaming** below); if
`synthesis.md` is missing or older than recent ingests, offer to run it.

**Transcripts are not optional polish.** Ingest always writes them so agents never need to re-OCR for exact strings. If step 1 does not fully answer the question, you **must** run step 2.

**Always search the entire documents root**, never just the topically-named folder. Real
processes cut across the taxonomy (benefits ↔ finances ↔ insurance ↔ providers; utility
dispute ↔ bank ↔ lawyers). Missing cross-folder IDs is the main failure mode this KB exists
to prevent.

1. **Find candidates** with ripgrep from the root:

   ```bash
   rg -l --glob '*.md' 'type: FolderSummary' /path/to/documents
   rg -i -C3 'vodafone|kündigungsfrist|aktenzeichen|vertragsnummer' /path/to/documents --glob '*.md'
   ```

2. **Read matching aggregates.** Frontmatter has `sources:`; body has orientation summary
   (folders with 2+ docs), then `## <Title>` sections with `_Source: <filename>_`.

3. **Fallback to transcripts** if the aggregate is thin (partial ID, missing amount, exact
   quote, “not sure”): search `.okf-transcripts/`, not the binary original and not a re-ingest
   unless the transcript is also missing:

   ```bash
   rg -i 'aktenzeichen|kundennummer|vertragsnummer' /path/to/documents/.okf-transcripts/
   ```

   Skipping this step when the MD is incomplete is a retrieval failure.

4. **Link matters over time** with IDs + git (see Change tracking). Prefer stable identifiers
   from the docs (Aktenzeichen, contract/customer/account numbers, invoice numbers, IBAN last
   4, case refs) as the join key across folders and commits:

   ```bash
   git -C /path/to/documents log --all --grep='123456789' -i
   git -C /path/to/documents log -S '123456789' -- '*.md'
   ```

5. **Answer** citing source **filenames** (provenance lines), not only the aggregate path.
   If the folder has more source files than `sources:` lists, offer re-ingest.

6. **Do not** use `.okf-llm-log.jsonl` to answer user questions about their documents.

If no aggregate exists for a relevant folder yet, offer to ingest first.

## Change tracking

Documents root is a git repo. After each ingest, **commit** so history is the version timeline.

**git = ingest/version timeline; aggregates = current distilled truth.** No changelogs inside
every `.md`. Case-event dates from the documents still live in the body as facts.

### Commit messages MUST include unique identifiers

When committing after ingest, put **stable IDs and short matter tags** in the commit subject/body
so agents (and you) can find the same matter months later even across folders:

```bash
# Good — greppable IDs + folders touched
git commit -m "Ingest 2026-07-18: ACME-Energy 123456789, TeleNet, InkassoCorp; providers+finances"

# Weak — date only, no join keys
git commit -m "Ingest: 2026-07-18"
```

Harvest IDs from the **new/changed aggregate sections** (and transcripts if needed): contract
numbers, customer numbers, Aktenzeichen, invoice/case refs, meter IDs, etc. Same IDs should
already appear in the Markdown bodies (extraction) so `rg` and `git log -S` both work.

Batch uploads → one commit still correlates co-arrival; **IDs in the message** correlate the
same matter across batches months apart (the other half of “two birds”).

```bash
git -C /path/to/documents log --stat
git -C /path/to/documents diff HEAD~1 -- '*.md'
git -C /path/to/documents log --grep='123456789' -i
```

Root-level per-matter files (**R2**, `<root>/matters/<slug>.md`) are written automatically by
the dream pass for any candidate group sharing a reference number — see **Dreaming** below.
Batch commits + shared IDs still matter for cases the free grouping pre-filter misses.

**Remote / web agents:** push to a **private** remote (Gitea, GitLab, …); they read `.md` +
git history, not raw PDFs. MCP is optional glue on a clone. See
[README — Remote access via git](README.md#remote-access-via-git).
Do not put personal case details in this skill file when documenting examples.

## Ingest

Requires an OpenAI-compatible LLM server (LM Studio, llama.cpp `llama-server`, Ollama, vLLM).
Check reachability before starting: `curl -s $SMART_OKF_LLM_HOST/v1/models`.

```bash
cd /home/oliver/Projects/smart-okf   # skill root — scripts import the app/ package
SMART_OKF_LLM_HOST=http://127.0.0.1:1234 \
SMART_OKF_LLM_MODEL=gemma-4-e4b-it-qat \
uv run python scripts/ingest_folder.py /path/to/documents
```

- Supported: `.pdf`, `.txt`, `.docx`, `.eml`, `.csv`, `.xlsx`, and images (`.png`/`.jpg`/`.jpeg`,
  read-only). Images use tesseract OCR by default (text only); pass `--vision-model <name>`
  (a vision-capable model served by the same host) for handwriting transcription plus a brief
  scene description instead — useful for things like a photographed utility meter reading where
  plain OCR misses handwritten digits. No extra dependency either way (two LLM calls per image
  when vision is on: describe, then structure).
- **PDF path (default = external marker):** layout-aware markdown via `marker_single` (not a
  pip dep of this skill — install with `pipx install marker-pdf`). Marker does its own layout
  OCR; it does **not** rewrite the PDF in place. **`--no-marker`:** pdfplumber + OCRmyPDF
  (deu+eng) embeds a searchable text layer into scanned PDFs once — later ingests and PDF
  editors reuse it. Standalone images are never modified — text lives in the transcript store
  and aggregate only.
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
- [marker](https://github.com/datalab-to/marker)'s `marker_single` is used by default for
  layout-aware PDF extraction (tables, forms) — see Prerequisites in [README.md](README.md).
  Pass `--no-marker` to skip it and use plain pdfplumber/OCRmyPDF instead. If marker was never
  installed and `--no-marker` isn't passed, ingest explicit-fails (not a silent quality
  downgrade) — install it or add the flag.
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

## Dreaming (cross-folder synthesis)

The librarian pass. After ingest has built/refreshed aggregates, run:

```bash
cd /path/to/smart-okf
uv run python scripts/dream.py /path/to/documents
```

- Writes one `<root>/synthesis.md` (`type: Synthesis`) with exactly four sections:
  **Matters** (same real-world affair across folders, joined by IDs), **Conflicts**
  (contradicting dates/amounts/statuses between aggregates), **Patterns**, **Open actions**.
- **Two passes.** A cheap scan reads a compact digest of **every** aggregate (identity,
  tags, orientation summary, section headings — not full bodies) and produces a baseline
  report. A free, non-LLM pre-filter then groups aggregates that share a reference number
  (contract/customer/meter/case ID — 5+ digit runs, matched in filenames/tags/summaries) into
  candidate matters; only those candidate groups get a follow-up call that reads their
  **full** aggregate text and replaces the baseline's Matters/Conflicts for that part of the
  report with fact-dense, ID-exact write-ups (Patterns always stays cheap-scan). Cost scales
  with the number of candidate groups, not tree size. No shared reference numbers anywhere →
  identical to the cheap-scan-only baseline, zero extra cost.
- **Each candidate group also gets its own file** — `<root>/matters/<slug>.md`
  (`type: Matter`), linking the involved aggregates plus the same deep-dive write-up. A
  stable, linkable concept per matter instead of only a paragraph in whichever `synthesis.md`
  happens to be current (this is **R2**; see step 0.5 below).
- **Incremental like ingest, per matter too**: aggregate hashes live in the synthesis
  frontmatter (whole-tree gate) *and* in each matter file's own frontmatter (per-matter gate)
  — a matter whose own aggregates are unchanged reuses its existing file and skips the
  deep-dive call even when an unrelated aggregate elsewhere triggered the run. `--force`
  re-dreams the whole tree anyway.
- **Dreamer model is its own choice** (`dream_model`/`dream_host` in config,
  `SMART_OKF_DREAM_MODEL`/`SMART_OKF_DREAM_HOST`, or `--model`/`--host`): falls back to the
  extractor model when unset, but reasoning quality scales with model size here more than
  anywhere else — see Onboarding step 4. Remote `dream_host` needs `allow_remote_llm`.
  Large KBs are synthesized in batches, then consolidated — transparent, no flag.
- Run it after ingest runs (same cron, one line later) or on demand when the user asks a
  cross-folder question and `synthesis.md` is stale/missing. Commit it with the ingest commit.
- The synthesis cites aggregate paths — treat it as a **map**, not a source of truth: verify
  facts in the cited aggregate (and its transcripts) before answering from it.

```cron
0 3 * * 0  cd /path/to/smart-okf && uv run python scripts/ingest_folder.py && uv run python scripts/dream.py
```

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

| Variable                   | Default                  | Purpose |
| -------------------------- | ------------------------ | ------- |
| `SMART_OKF_LLM_HOST`     | `http://localhost:11434` | Extractor: OpenAI-compatible `/v1/chat/completions` server |
| `SMART_OKF_LLM_MODEL`    | `qwen2.5:3b`             | Extractor model name as the server reports it |
| `SMART_OKF_LLM_API_KEY`  | `not-needed`             | Only for servers that require auth |
| `SMART_OKF_VISION_MODEL` | unset                    | Optional vision model on the same host for images |
| `SMART_OKF_CONFIG`       | `smart-okf.yaml`         | Path to YAML config |

Remote (non-localhost/RFC1918) LLM hosts are refused unless `allow_remote_llm` is set — keeps
raw document text off the cloud by default. The orchestrating agent can still be a cloud model;
it only sees aggregates/transcripts you choose to open, not the ingest subprocess payload.
