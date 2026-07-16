# Coding Standards — smart-okf

Baseline conventions for all agents in this repo.
**Quick checklist:** [`rules/common/coding-style.md`](rules/common/coding-style.md)

Python specifics: [`PYTHON_STANDARDS.md`](PYTHON_STANDARDS.md)  
Architecture: [`docs/DESIGN.md`](docs/DESIGN.md)

---

## Principles

1. **Readability first** — clear names, self-documenting structure.
2. **KISS** — simplest solution; no premature abstraction.
3. **DRY** — shared logic in `app/services/`; one ingest path for CLI, UI, API, MCP.
4. **YAGNI** — build Phase 0–1 before speculative Phase 4 features.
5. **Focused diffs** — only change what the task requires; match existing patterns.

---

## Error handling

- Services raise typed exceptions from `app/exceptions.py`
- CLI/UI catch, log, and continue or surface to user — no silent `print` + magic strings
- Validate paths before any KB write (see design: `validate_kb_path`)

---

## Code smells to avoid

| Smell | Fix |
|-------|-----|
| Long functions (>50 lines) | Extract helpers in same module or `services/` |
| Deep nesting | Early returns / guard clauses |
| Magic numbers/strings | `app/constants.py` |
| Duplicate ingest/OCR logic | `app/services/ingest.py`, `text_extraction.py` |
| Mutating Pydantic models in place | `model_copy(update=...)` |

---

## Testing

- AAA pattern: Arrange, Act, Assert
- Descriptive test names: `test_apply_ingest_defaults_fills_missing_provenance_without_mutation`
- Add tests when changing OKF models, ingest, or enrichment behavior

---

## Documentation

- Explain **why**, not what, in comments
- Update `DEVELOPMENT_PLAN.md` checkboxes when completing roadmap items
- Design changes: update `docs/DESIGN.md` or note in PR description