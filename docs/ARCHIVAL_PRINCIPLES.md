# Archival principles behind smart-okf

smart-okf is not "an LLM dumped into a folder." Its layering is a direct application of
archival and library-science method (Archiv-/Bibliothekswissenschaft). This document is
self-contained — the principles are stated here, not by reference to any external skill —
so the reasoning ships with the code.

The one rule that overrides everything: **smart-okf is non-destructive.** It reads a
document tree in place and builds a knowledge layer on top. It never renames, moves, or
deletes the user's source documents. Reorganizing the files themselves is a separate
concern (a file-organization task), deliberately kept out of this tool.

## The three principles and where each lives

### 1. Provenienzprinzip (principle of provenance) — the aggregate + roll-up layer

Records are kept and described in the structure in which they arose; the context of
origin is itself information and is not dissolved into a thematic re-sort. In smart-okf:

- Each folder gets exactly one aggregate (`type: FolderSummary`) covering the documents
  directly inside it — the folder-of-origin is respected as given.
- A folder with subfolders gets a roll-up: its aggregate (or a `type: FolderIndex` file
  when it has no documents of its own) links down to each child. Every level of the
  hierarchy describes the level beneath it, so the tree stays navigable top-to-bottom —
  the archival *Findbuch* (finding aid) applied to a filesystem.
- The roll-up **links**, it never re-summarizes: a parent points at its children with a
  one-line description each and does not inline their content. This keeps the description
  at each level about *that* level, and keeps re-ingest incremental (a changed child
  doesn't force its parent to be re-extracted).

### 2. Pertinenzprinzip (principle of pertinence) — the dream / matters layer

The complementary principle: records are grouped by subject/matter (Betreff) regardless of
where they physically sit. A dispute with an energy provider touches `providers/`,
`finances/`, `insurance/`, and `lawyers/` — provenance keeps those apart, pertinence pulls
the thread together. In smart-okf this is the `dream` pass: it correlates aggregates across
folders by shared identifiers (contract/customer/case numbers) into *matters*
(`type: Matter`) and a whole-tree `synthesis.md`, without touching the folders themselves.

Both layers always exist — the two principles are complementary, not either/or. The
`ordering_principle` config setting only tunes the *balance*: `provenance` (default) forms
matters conservatively (only strong, longer shared identifiers), `pertinence` forms them
eagerly (shorter shared identifiers also count), so a user whose retrieval is more
subject-driven than folder-driven gets more cross-folder synthesis. Concretely it sets the
minimum shared-identifier digit length in `app/services/matter_grouping.py`.

### 3. Findbuch-Prinzip (finding aid) — the navigation README

At the very top, a human-facing `README.md` is regenerated on every ingest: per-folder
links plus at-a-glance statistics, browsable in a file UI (Nextcloud, a git host). Like a
finding aid, it is an index into the holdings, not a copy of them — it points, it does not
duplicate. It never overwrites a hand-written README (it writes only a file bearing its own
generated marker).

## Kassation (appraisal / weeding) — gating

Archival practice does not keep everything at full effort: appraisal decides what is worth
retaining and at what depth. smart-okf's gating (`app/services/gating.py`) is the same idea:

- **Exclude**: documents with no durable personal facts (manuals, terms of service,
  marketing) can be dropped from ingest entirely via patterns.
- **Deprioritize (eager)**: anything matching a built-in low-value keyword (AGB,
  Bedienungsanleitung, …) or a user low-priority pattern is still ingested but kept out of
  the expensive cross-folder `dream` pass — unless explicitly marked priority. The default
  stance leans toward *not* spending deep-analysis budget on boilerplate.
- **Password-protected files** are skipped and logged rather than half-read or crashing.

## What onboarding asks

Because more than one principle can legitimately govern, the choice is not assumed — the
onboarding interview asks for the governing `ordering_principle` (respect folders as-is, or
lean into cross-folder matters) and for any exclude/low-priority/priority patterns, and
records them in `smart-okf.yaml`.
