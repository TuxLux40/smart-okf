"""Application configuration: YAML file + environment variable loading.

Load order (lowest to highest precedence): field defaults -> .smart-okf/config.yaml -> env vars
(`SMART_OKF_` prefix). One config lives *inside* the document root it describes (a hidden
`.smart-okf/` folder), not on the machine running the scripts — so it travels with the tree
(e.g. over a private git remote to another agent/machine) instead of staying behind. Use
`load_config(root)` to load a specific root's config; scripts always take a folder argument.
"""

import contextvars
import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import Field, ValidationError, ValidationInfo, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from app.constants import (
    DEFAULT_LLM_HOST,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
)

CONFIG_DIR_NAME = ".smart-okf"
CONFIG_FILENAME = "config.yaml"
DEFAULT_LLM_HOST_ALLOWLIST = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
ALWAYS_ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

_config_path_override: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "_config_path_override", default=None
)
"""Set by `load_config()` for the duration of one `SmartOkfConfig()` construction so
`YamlConfigSettingsSource` knows which root's config to read — pydantic-settings gives a
source no way to receive a per-call argument directly."""


def config_path_for_root(root: Path) -> Path:
    """Where a document root's config lives: `<root>/.smart-okf/config.yaml`."""
    return root / CONFIG_DIR_NAME / CONFIG_FILENAME


def find_config_path(start: Path) -> Path | None:
    """Walk `start` and its parents up to the filesystem root looking for
    `.smart-okf/config.yaml`. Callers may legitimately point scripts at a subfolder of an
    already-onboarded document root (e.g. an ingest smoke test on one subfolder, per
    SKILL.md) — the config still lives at the root, not in that subfolder, so a literal
    `start / CONFIG_DIR_NAME / CONFIG_FILENAME` check alone would miss it and silently fall
    back to built-in defaults instead of the user's actual settings.
    """
    for candidate in (start, *start.parents):
        config_path = config_path_for_root(candidate)
        if config_path.is_file():
            return config_path
    return None


def resolve_document_root(start: Path) -> Path:
    """The true document root for `start`: the ancestor holding `.smart-okf/config.yaml`,
    or `start` itself if none is found (fresh/unconfigured root).

    Scripts may legitimately be pointed at a subfolder of an already-onboarded root (an
    ingest smoke test on one subfolder, per SKILL.md) — root-level artifacts like
    `.okf-llm-log.jsonl` should still land at the real root every time, not scatter into
    whatever subfolder a given invocation happened to target. Without this, running
    ingest against `documents/finances` one day and `documents/health` another leaves N
    fragmented logs instead of one, and folders never targeted directly (e.g. a root-level
    `documents/other` nobody explicitly ingested) end up with no log at all even though
    ingest ran elsewhere in the same tree.
    """
    config_path = find_config_path(start)
    if config_path is not None:
        return config_path.parent.parent
    return start


def parse_llm_host(value: str) -> str:
    """Extract a bare hostname from a URL or `host:port` string.

    `http://localhost:11434` -> `localhost`; `localhost:11434` -> `localhost`.
    """
    if "://" in value:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"Invalid llm_host URL: {value}")
        return parsed.hostname
    return value.split(":")[0]


def _is_rfc1918(hostname: str) -> bool:
    try:
        return ipaddress.ip_address(hostname).is_private
    except ValueError:
        return False


def host_is_allowlisted(hostname: str, extra: list[str]) -> bool:
    """True if `hostname` is always-allowed, RFC1918 private, or in `extra`."""
    if hostname in ALWAYS_ALLOWED_HOSTNAMES:
        return True
    if _is_rfc1918(hostname):
        return True
    return hostname in extra


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Load a document root's `.smart-okf/config.yaml` via pyyaml.

    Path comes from `_config_path_override` (set by `load_config(root)`), falling back to
    the `SMART_OKF_CONFIG` env var for callers that want an explicit override (tests, or a
    config file kept somewhere other than the root it describes).
    """

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = _config_path_override.get()
        if path is None:
            env_override = os.getenv("SMART_OKF_CONFIG")
            path = Path(env_override) if env_override else None
        if path is not None and path.exists():
            return yaml.safe_load(path.read_text()) or {}
        return {}


class SmartOkfConfig(BaseSettings):
    """Root application configuration.

    Trimmed to fields the actual pipeline (`app/services/ingest.py`) reads. Fields from
    the pre-rewrite design (colocation_mode, watcher_*, sqlite_path, bind_host/port, ...)
    were removed as dead config — see the 2026-07-17/18 amendments in docs/DESIGN.md for
    why those subsystems were cut. Re-add fields here only when the code that reads them
    actually exists.
    """

    model_config = SettingsConfigDict(env_prefix="SMART_OKF_", env_nested_delimiter="__")

    llm_model: str = DEFAULT_LLM_MODEL
    llm_temperature: float = DEFAULT_LLM_TEMPERATURE
    llm_max_tokens: int = DEFAULT_MAX_TOKENS
    allow_remote_llm: bool = False
    llm_host_allowlist: list[str] = Field(default_factory=lambda: list(DEFAULT_LLM_HOST_ALLOWLIST))
    llm_host: str = DEFAULT_LLM_HOST

    use_marker: bool = True
    """Route PDF extraction through the marker CLI backend (layout-aware: tables, forms).
    Requires a separately-installed `marker_single` binary on PATH — never a pip
    dependency of this project (marker's code is GPL-3.0); onboarding installs it as a
    prerequisite alongside tesseract/ghostscript. Set false (CLI: `--no-marker`) to opt
    out and use plain pdfplumber/OCRmyPDF instead. See README.md."""

    vision_model: str | None = None
    """Vision-capable model name for standalone image ingest (handwriting transcription +
    scene description), served by the same `llm_host`. None (default) falls back to
    tesseract-only OCR — no vision capability, no dependency added. See README.md."""

    dream_model: str | None = None
    """Model for the dream synthesis pass (`scripts/dream.py`). None (default) uses
    `llm_model`. Dreaming is cross-folder *reasoning*, not extraction — it benefits from
    the smartest model available more than any other stage, so users with stronger
    hardware (or willingness to use a hosted model, see `dream_host`) point this at a
    bigger model than the extractor."""

    dream_host: str | None = None
    """Server for the dream model. None (default) uses `llm_host`. Subject to the same
    remote-host gate as `llm_host` (`allow_remote_llm` + allowlist): dream input is
    digests of personal aggregates — distilled, but still personal data."""

    verify_model: str | None = None
    """Model for mandatory post-extraction fact verification (`app/services/fact_verification.py`).
    None (default) uses `llm_model` — the same model verifies its own output, which catches
    obviously-broken shapes (fabrication, template echo) but can't catch a mistake the same
    model is systematically prone to; point this at a different/bigger model if the extractor
    is weak enough that self-verification isn't trustworthy."""

    verify_host: str | None = None
    """Server for the verify model. None (default) uses `llm_host`. Subject to the same
    remote-host gate as `llm_host` (`allow_remote_llm` + allowlist): verification input is
    the same raw source text the extractor already saw."""

    exclude_patterns: list[str] = Field(default_factory=list)
    """Glob patterns (root-relative path or bare filename) for files never ingested — e.g.
    `["*handbuch*", "*/AGB/*"]`. For documents with no durable personal facts (manuals,
    terms, marketing). See `app/services/gating.py`."""

    low_priority_patterns: list[str] = Field(default_factory=list)
    """Glob patterns for files ingested normally but kept out of the deep `dream` pass."""

    priority_patterns: list[str] = Field(default_factory=list)
    """Glob patterns forcing deep analysis — overrides low-priority patterns and the
    built-in trivial-name heuristic (`gating.DEFAULT_TRIVIAL_KEYWORDS`)."""

    ordering_principle: str = "provenance"
    """Governing archival principle (asked at onboarding, see docs/ARCHIVAL_PRINCIPLES.md).
    `provenance` (default, conservative): respect the folder-of-origin structure; only
    strong cross-folder ID matches form matters. `pertinence` (eager): lean harder on
    cross-folder subject synthesis — weaker ID matches also form matters. Concretely tunes
    the minimum shared-identifier length in `matter_grouping`."""

    derive_per_file: bool = False
    """Also emit one derived-facts file per source document (`.okf-facts/<file>.md`) in
    addition to the facts already written into the folder aggregate. Off by default: the
    aggregate is the primary artifact; per-file files are for callers who want them."""

    generate_readme: bool = True
    """Write/refresh a human-facing `README.md` at the documents root after ingest — a
    self-updating navigation index with per-folder links and at-a-glance statistics
    (browsable in a file UI / Nextcloud). See `app/services/navigation.py`."""

    @field_validator("ordering_principle")
    @classmethod
    def validate_ordering_principle(cls, v: str) -> str:
        """Only the two archival ordering principles are valid."""
        if v not in {"provenance", "pertinence"}:
            raise ValueError(f"ordering_principle must be 'provenance' or 'pertinence', got {v!r}")
        return v

    @field_validator("llm_host", "dream_host", "verify_host")
    @classmethod
    def validate_llm_host(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Reject non-allowlisted remote hosts unless `allow_remote_llm` is set."""
        if v is None:
            return v
        hostname = parse_llm_host(v)
        if host_is_allowlisted(hostname, info.data.get("llm_host_allowlist", [])):
            return v
        if info.data.get("allow_remote_llm"):
            return v
        raise ValueError(f"{info.field_name} hostname {hostname!r} not in allowlist; set allow_remote_llm=true")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls))


def load_config(root: Path) -> SmartOkfConfig | None:
    """Load the config for one document root: `<root>/.smart-okf/config.yaml`, or the
    nearest ancestor's if `root` is a subfolder of an already-onboarded root (see
    `find_config_path`). Env vars (`SMART_OKF_*`) still override. `SMART_OKF_CONFIG` can
    point at a file somewhere else entirely (tests, or a config kept outside the root it
    describes) and wins over both. None if no config file is found (at `root` or any
    ancestor) or it fails validation — every field has a default, so callers can't tell
    "no config" from "all defaults" any other way.
    """
    env_override = os.getenv("SMART_OKF_CONFIG")
    config_path = Path(env_override) if env_override else find_config_path(root)
    if config_path is None or not config_path.is_file():
        return None
    token = _config_path_override.set(config_path)
    try:
        return SmartOkfConfig()
    except ValidationError:
        return None
    finally:
        _config_path_override.reset(token)
