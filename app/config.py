"""Application configuration: YAML file + environment variable loading.

Load order (lowest to highest precedence): field defaults -> smart-okf.yaml -> env vars
(`SMART_OKF_` prefix).
"""

import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import Field, ValidationInfo, field_validator
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

DEFAULT_CONFIG_FILENAME = "smart-okf.yaml"
DEFAULT_LLM_HOST_ALLOWLIST = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
ALWAYS_ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


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
    """Load `smart-okf.yaml` (or `~/.config/smart-okf/smart-okf.yaml`) via pyyaml."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = Path(os.getenv("SMART_OKF_CONFIG", DEFAULT_CONFIG_FILENAME))
        if not path.exists():
            path = Path.home() / ".config/smart-okf" / DEFAULT_CONFIG_FILENAME
        if path.exists():
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

    document_roots: list[Path] = Field(..., min_length=1)

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

    @field_validator("document_roots", mode="before")
    @classmethod
    def validate_document_roots(cls, v: list[Path | str]) -> list[Path]:
        """Require at least one root; normalize to resolved absolute paths."""
        roots = [Path(p).expanduser().resolve() for p in (v or [])]
        if len(roots) < 1:
            raise ValueError("document_roots must contain at least one path")
        return roots

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
