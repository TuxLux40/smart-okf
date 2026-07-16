# Agent Guides — smart-okf

Persistent reference docs for coding agents (Cursor, Copilot, Cline, Windsurf, OpenCode, etc.).
Read the relevant guide **before** changing code in that area.

| Topic | Full guide | Quick reference |
|-------|------------|-----------------|
| **Coding (shared)** | [`CODING_STANDARDS.md`](CODING_STANDARDS.md) | [`rules/common/coding-style.md`](rules/common/coding-style.md) |
| **Python code style** | [`PYTHON_STANDARDS.md`](PYTHON_STANDARDS.md) | [`rules/common/python-style.md`](rules/common/python-style.md) |
| **Python type safety** | [`PYTHON_TYPE_SAFETY.md`](PYTHON_TYPE_SAFETY.md) | [`rules/common/python-types.md`](rules/common/python-types.md) |
| **System design (Phase 0–3)** | [`docs/DESIGN.md`](docs/DESIGN.md) | PR Plan + Key Decisions sections |

## Project context

| Doc | Contents |
|-----|----------|
| [`AGENTS.md`](AGENTS.md) | Architecture, commands, module map |
| [`README.md`](README.md) | Overview, quick start |
| [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) | Phased roadmap |

## IDE-specific pointers

| Agent | Location |
|-------|----------|
| Cursor | `.cursor/rules/` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Cline | `.clinerules/` |
| Windsurf | `.windsurf/rules/` |
| OpenCode | `.opencode/AGENTS.md` |

## Workflows (session skills, not persisted as rules)

- **`/design`** — design-doc writer/reviewer loop; deliverable lands in `docs/DESIGN.md` when committed
- **`/caveman-init`** — terse communication rules; see `.cursor/rules/caveman.mdc` and peers
- **`/python-code-style`** — ruff/mypy/pytest; see `PYTHON_STANDARDS.md` and `.github/workflows/python.yml`
- **`/python-type-safety`** — strict mypy, protocols, aliases; see `PYTHON_TYPE_SAFETY.md`