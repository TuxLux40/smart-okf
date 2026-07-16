# Python Standards — smart-okf

Conventions for the Python backend (`app/`, `scripts/`, `tests/`).
**Quick checklist:** [`rules/common/python-style.md`](rules/common/python-style.md)

Shared quality rules: [`CODING_STANDARDS.md`](CODING_STANDARDS.md).  
Type safety: [`PYTHON_TYPE_SAFETY.md`](PYTHON_TYPE_SAFETY.md).

---

## Tooling

Configured in `pyproject.toml`:

| Tool | Purpose |
|------|---------|
| **ruff** | Lint + format |
| **mypy** | Strict static type checking |
| **pytest** | Unit and integration tests |

```bash
uv sync --group dev
uv run ruff check --fix .
uv run ruff format .
uv run mypy app scripts tests
uv run pytest -q
```

- Line length: **120**
- Target: **Python 3.11+** (mypy `python_version = "3.12"`)
- mypy: `strict = true` (relaxed for `tests.*`)
- E501 ignored — formatter handles line length

---

## Code style

### Naming (PEP 8)

| Kind | Style | Examples |
|------|-------|----------|
| Modules | `snake_case` | `kb_manager.py`, `text_extraction.py` |
| Classes | `PascalCase` | `OKFDocument`, `LLMClient` |
| Functions | `snake_case` | `ingest_document_file`, `load_prompt` |
| Constants | `SCREAMING_SNAKE` | `DEFAULT_LLM_MODEL`, `SUPPORTED_DOCUMENT_SUFFIXES` |

### Imports

Order: stdlib → third-party → local (`app.*`). Absolute imports only.

### Types

- Modern syntax: `str | None`, `list[str]`, not `Optional` / `List`
- Type hints on all public APIs
- Raise typed exceptions (`LLMClientError`, `DocumentIngestError`) — do not return error strings from services

### Immutability

- Prefer `model_copy(update=...)` on Pydantic models
- Avoid in-place mutation of shared models (deprecate `OKFDocument.add_link()` in favor of `with_link()` per design)

### Docstrings

Google style on public classes, methods, and module-level functions.

### Constants

Centralize magic values in `app/constants.py`. Do not scatter defaults across UI and services.

---

## Layout

```
app/
  constants.py       # shared defaults
  exceptions.py      # SmartOkfError hierarchy
  models/            # Pydantic / OKF models
  services/          # business logic (ingest, llm, prompts, text_extraction, …)
  ui/                # Streamlit
scripts/             # CLI entrypoints
tests/               # pytest
prompts/             # LLM system prompts (markdown)
```

CLI and UI call `app.services` — no duplicated pipeline logic in scripts.

---

## Verification before claiming done

```bash
uv run ruff check .
uv run mypy app scripts tests
uv run pytest -q
```