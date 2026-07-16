# Python Style — Quick Reference

Full guide: [`PYTHON_STANDARDS.md`](../../PYTHON_STANDARDS.md) · Scope: `app/`, `scripts/`, `tests/`

## Verify

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts tests && uv run pytest -q
```

## Always

- `str | None`, `list[str]` — modern types
- Strict types on public APIs
- Google docstrings on public services/models
- Constants in `app/constants.py`
- Typed exceptions — no `[LLM Error]` string returns
- `model_copy` for Pydantic updates

## Naming

`snake_case` functions/modules · `PascalCase` classes · `SCREAMING_SNAKE` constants

## Imports

stdlib → third-party → `app.*` (absolute only)