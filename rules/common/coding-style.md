# Coding Style — Quick Reference

Full guide: [`CODING_STANDARDS.md`](../../CODING_STANDARDS.md)

## Principles

Readability · KISS · DRY · YAGNI · focused diffs

## Python project rules

- Business logic in `app/services/` — thin `scripts/` and `app/ui/`
- Shared ingest via `app/services/ingest.py`
- Path validation before KB writes
- Tests for model/ingest changes (AAA, descriptive names)

## Before done

```bash
uv run ruff check . && uv run mypy app scripts tests && uv run pytest -q
```