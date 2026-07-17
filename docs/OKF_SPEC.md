# OKF conventions for smart-okf

Canonical reference: [OKF v0.1 spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(Google's `knowledge-catalog` repo — the format's origin). The [catancs/okf-skill](https://github.com/catancs/okf-skill)
agent skill is a simplified restatement of the same spec; where the two disagree, this doc follows
the origin spec.

This is the canonical statement of the file structure and content rules `app/models/okf.py`,
`app/services/ingest.py`, and the future KB manager (PR 2+) must uphold. Update this doc, not just
the code, when a rule changes.

## Terminology (from the spec)

- **Bundle** — the whole tree of markdown files. In smart-okf, each document root is a bundle.
- **Concept** — one unit of knowledge = one markdown file (frontmatter + body). Every `.md` file
  except `index.md` and `log.md` is a concept.
- **Concept ID** — the file's path within the bundle, `.md` suffix removed (`tables/orders.md` → `tables/orders`).

## Bundle structure

smart-okf uses **co-located companions** (`file.pdf` → `file.md`) — the bundle lives inside the
document folders themselves rather than a separate `knowledge/` tree:

```
documents/
├── index.md              # planned (PR 2): directory listing, no frontmatter (see below)
├── contract.pdf
├── contract.md           # concept: companion to contract.pdf
├── genealogy/
│   ├── index.md
│   ├── birth.pdf
│   └── birth.md
```

## Reserved filenames

`index.md` and `log.md` are reserved at every level of the hierarchy and MUST NOT be used as
concept names. Enforced in code by `app/constants.RESERVED_CONCEPT_FILENAMES` —
`ingest_document_file` raises `DocumentIngestError` rather than silently overwrite one (e.g. a
source file literally named `index.pdf` would otherwise produce a companion named `index.md`).

## Concept documents

YAML frontmatter (delimited by `---`) + markdown body. Modeled by `OKFFrontmatter` / `OKFDocument`
in `app/models/okf.py`.

**Required:** `type` — a short descriptive string. Not centrally registered; consumers must
tolerate unknown values.

**Recommended:** `title`, `description` (used by index/search — always set it), `resource` (URI
for an underlying asset, if any), `tags`, `timestamp`.

**smart-okf extension field (not in upstream OKF v0.1):** `source` — relative path to the
original ingested file. Required for anything produced by `app/services/ingest.py`; this is our
provenance mechanism since we ingest local documents rather than cataloging existing resources.

**`okf_version`:** per §11 of the spec, this belongs only in a bundle-root `index.md`'s
frontmatter (the one exception where `index.md` carries frontmatter) — not on every concept.
`OKFFrontmatter.okf_version` defaults to `None` and is only set when a document explicitly opts in.

```markdown
---
type: Fact                     # REQUIRED
title: Birth Date              # Recommended
description: Recorded birth date  # Recommended
source: genealogy/birth.pdf    # smart-okf extension — provenance
tags: [genealogy]
timestamp: 2026-06-17T00:00:00Z
---

## Key Facts
- Born 1901

## Related
- [Birth Certificate](./birth-certificate.md)
```

Conventional body headings from the spec (use when applicable): `# Schema` (columns/fields),
`# Examples`, `# Citations` (numbered external sources backing a claim). smart-okf additionally
uses `## Related` (`RELATED_SECTION_HEADING`) as the convention `OKFDocument.add_link()` appends
to — this is our own link-collection convention layered on top of the spec's plain body links.

## Cross-linking

- **Absolute (bundle-relative):** `[text](/tables/customers.md)` — resolved from the document
  root; the spec's recommended form since it survives moves within a subdirectory.
- **Relative:** `[text](./other.md)`.
- Links assert a relationship; the kind of relationship is conveyed by prose, not the link.
  Consumers MUST tolerate broken links.

## Index files (`index.md`)

Per §6: **no frontmatter** (except the bundle-root exception above), body only. Lists concepts
under one or more headings, description pulled from each concept's frontmatter:

```markdown
# Section / Group Heading

* [Title 1](relative-url-1) - short description of item 1
* [Title 2](relative-url-2) - short description of item 2
```

Not yet generated automatically — planned for PR 2 (`KBManager`).

## Log files (`log.md`, optional)

Per §7: flat, date-grouped history, newest first, ISO 8601 `YYYY-MM-DD` headings:

```markdown
# Directory Update Log

## 2026-05-22
* **Update**: Added new table reference for [Customer Metrics](/tables/customer-metrics.md).
* **Creation**: Established the [Dataplex Playbook](/playbooks/dataplex.md).
```

Not yet generated — a natural fit for the Dream pass (PR 9) recording what it changed.

## Conformance (§9)

A bundle is conformant if every non-reserved `.md` file has parseable frontmatter with a
non-empty `type`, and reserved files follow the index/log structure above when present. Everything
else — missing optional fields, unknown types, broken links, missing `index.md` — is soft
guidance, not a rejection reason. `app/services/validation.py` (planned, PR 4) checks this.

## Types (smart-okf vocabulary)

Personal/sensitive-document domain, not the data-catalog domain the spec's own examples target
(`BigQuery Table`, etc.) — `type` is a free string (`extra: allow`); consumers handle unknown
types gracefully:

| Type | Use for |
|------|---------|
| `Fact` | An atomic, sourced statement |
| `Event` | Something that happened, with a date |
| `Person` | An entity/person profile |
| `DocumentSummary` | Extraction summary for one ingested document |
| `Index` | A directory listing (`index.md`) |
| `Insight` | Derived/inductive conclusion (Dream pass) |
| `Pattern` | Cross-document pattern or abstraction (Dream pass) |

Add project-specific types as needed; do not enforce an enum.

## Workflow (Honcho-inspired: store → derive → dream → query)

1. **Store** — ingest writes the co-located concept `.md` with provenance (`app/services/ingest.py`).
2. **Derive** — on ingest, extract explicit facts + immediate deductions (planned: PR 8).
3. **Dream** — periodic pass over the KB for patterns, conflicts, links, abstractions; a natural
   writer of `log.md` entries (planned: PR 9).
4. **Query** — humans browse folders directly; agents use ripgrep, index/companion links, or the
   future API/MCP tools (planned: PR 5, PR 12, PR 15).
