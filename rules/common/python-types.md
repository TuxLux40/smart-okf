# Python Type Safety — Quick Reference

Full guide: [`PYTHON_TYPE_SAFETY.md`](../../PYTHON_TYPE_SAFETY.md)

## Verify

```bash
uv run mypy app scripts tests
```

## Always

- Public APIs fully annotated
- `T | None` not `Optional[T]`
- No `Any` unless truly dynamic (document why)
- `app/types.py` for shared aliases
- `Protocol` in `app/services/ports.py` for swappable services
- Narrow with `if x is None: raise` before use

## Avoid

- `**kwargs: Any` — use explicit keyword-only params
- Bare `dict` — prefer `dict[str, str]` or a `TypeAlias`
- Silent `# type: ignore`