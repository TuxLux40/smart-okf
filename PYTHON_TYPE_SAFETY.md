# Python Type Safety — smart-okf

Type-checking conventions for `app/`, `scripts/`, `tests/`.
**Quick checklist:** [`rules/common/python-types.md`](rules/common/python-types.md)

Style and formatting: [`PYTHON_STANDARDS.md`](PYTHON_STANDARDS.md)

---

## Tooling

Strict mypy in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
```

```bash
uv run mypy app scripts tests
```

CI runs the same check (`.github/workflows/python.yml`).

---

## Rules

### Annotate all public APIs

Every public function, method, and class attribute needs types. Return `None` explicitly where applicable.

### Modern unions

Use `T | None`, not `Optional[T]`. Use `list[str]`, not `List[str]`.

### Minimize `Any`

- Prefer explicit keyword parameters over `**kwargs: Any`
- Use `TypeAlias` in `app/types.py` for repeated string roles
- Pydantic `model_validate` / `model_copy` at untyped boundaries (YAML, LLM text)

### Type narrowing

Guard before use:

```python
user = find_user(user_id)
if user is None:
    raise NotFoundError(user_id)
return user.name  # mypy knows user is User
```

### Protocols for ports

Service boundaries use `typing.Protocol` in `app/services/ports.py` (e.g. `ReviewQueuePort`). Implementations swap without inheritance.

### Generics and bounds

When adding reusable containers, use `TypeVar` with `bound=BaseModel` for Pydantic models.

---

## Layout

| Module | Purpose |
|--------|---------|
| `app/types.py` | `TypeAlias` names (`RelativePath`, `MarkdownContent`, …) |
| `app/services/ports.py` | Structural protocols |
| `app/models/` | Pydantic models (runtime + static types) |

---

## Verification

```bash
uv run mypy app scripts tests
```

No `# type: ignore` without a one-line comment explaining why.